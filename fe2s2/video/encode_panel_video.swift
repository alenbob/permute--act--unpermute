// Encode scientific plot frames using the system H.264 encoder, without a
// dependency on ffmpeg. Usage: swift encode_panel_video.swift FRAMES OUTPUT FPS
import Foundation
import AVFoundation
import CoreGraphics
import ImageIO

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}
let args = CommandLine.arguments
guard args.count == 4, let fps = Int32(args[3]), fps > 0 else {
    fail("Expected frames directory, MP4 output, positive integer FPS")
}
let directory = URL(fileURLWithPath: args[1])
let destination = URL(fileURLWithPath: args[2])
let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
    .filter { $0.pathExtension == "png" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
guard let first = files.first,
    let firstSource = CGImageSourceCreateWithURL(first as CFURL, nil),
    let firstImage = CGImageSourceCreateImageAtIndex(firstSource, 0, nil) else { fail("No PNG frames") }
let width = firstImage.width, height = firstImage.height
if FileManager.default.fileExists(atPath: destination.path) { try FileManager.default.removeItem(at: destination) }
let writer = try AVAssetWriter(outputURL: destination, fileType: .mp4)
writer.shouldOptimizeForNetworkUse = true
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264,
    AVVideoWidthKey: width,
    AVVideoHeightKey: height,
    AVVideoCompressionPropertiesKey: [
        // About 5 Mbit/s at 1080 x 840, scaled with the pixel count.
        AVVideoAverageBitRateKey: 5_000_000*width*height/(1080*840),
        AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
        AVVideoExpectedSourceFrameRateKey: fps,
        AVVideoMaxKeyFrameIntervalKey: fps
    ]
])
input.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
    kCVPixelBufferWidthKey as String: width,
    kCVPixelBufferHeightKey as String: height,
    kCVPixelBufferCGImageCompatibilityKey as String: true,
    kCVPixelBufferCGBitmapContextCompatibilityKey as String: true
])
guard writer.canAdd(input) else { fail("Cannot add video track") }
writer.add(input)
guard writer.startWriting() else { fail("Cannot start encoder: \(String(describing: writer.error))") }
writer.startSession(atSourceTime: .zero)
for (index, file) in files.enumerated() {
    while !input.isReadyForMoreMediaData {
        if writer.status == .failed { fail("Encoder failed: \(String(describing: writer.error))") }
        Thread.sleep(forTimeInterval: 0.002)
    }
    try autoreleasepool {
        guard let source = CGImageSourceCreateWithURL(file as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
              image.width == width, image.height == height,
              let pool = adaptor.pixelBufferPool else { fail("Invalid frame: \(file.path)") }
        var optionalBuffer: CVPixelBuffer?
        guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &optionalBuffer) == kCVReturnSuccess,
              let buffer = optionalBuffer else { fail("Cannot allocate frame") }
        CVPixelBufferLockBaseAddress(buffer, [])
        guard let context = CGContext(data: CVPixelBufferGetBaseAddress(buffer), width: width, height: height,
            bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue) else {
            fail("Cannot draw frame")
        }
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        CVPixelBufferUnlockBaseAddress(buffer, [])
        guard adaptor.append(buffer, withPresentationTime: CMTime(value: Int64(index), timescale: fps)) else {
            fail("Cannot append frame: \(String(describing: writer.error))")
        }
    }
}
input.markAsFinished()
writer.endSession(atSourceTime: CMTime(value: Int64(files.count), timescale: fps))
let completion = DispatchSemaphore(value: 0)
writer.finishWriting { completion.signal() }
completion.wait()
guard writer.status == .completed else { fail("Incomplete MP4: \(String(describing: writer.error))") }
print("Encoded \(files.count) frames at \(fps) fps: \(destination.path)")
