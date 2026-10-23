"""Reproduce the Fe2S2 resource video from the bundled numerical snapshot."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import math
import platform
import shutil
import subprocess
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.offsetbox import AnnotationBbox, HPacker, OffsetImage, TextArea
from matplotlib.path import Path as MplPath
from matplotlib.patches import Polygon, Rectangle
from matplotlib.text import Text
from matplotlib.transforms import Affine2D
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SERIES = ['Frame SELECT','Frame extension','PAU','PAU multiple']
from check_data import check_data

# The video omits the multiple-family PAU series; the main plot keeps it.
OMITTED = ('PAU multiple',)
SHOWN = [k for k in SERIES if k not in OMITTED]
# Export-only shapes: a hollow circle for Frame SELECT, a hollow square for
# single-family PAU, and a salmon diamond with an off-black border for Frame
# SELECT with our optimizations. The main plot keeps SERIES.
MARKERS = {'Frame SELECT': 'o', 'Frame extension': 'D', 'PAU': 's'}
FILLED = {'Frame extension'}
assert list(MARKERS) == SHOWN and FILLED <= MARKERS.keys()

# Alice & Bob dark surface: salmon for the Frame SELECT (Anthropic + QuEra)
# series, the yellow hero for permute act unpermute; white text on off-black.
FRAME_COLOR, PAU_COLOR = '#FB6168', '#FED731'
OFF_BLACK, WHITE, CARD_DARK, SECONDARY_INVERSE = '#010102', '#FFFFFF', '#0A0A0C', '#C7CDD3'
PAU_TEXT_COLOR = OFF_BLACK
# Fill opacity of the origin rectangles: yellow is near-opaque so it reads as
# saturated on off-black; salmon keeps the main plot's 25% and is layered
# above the yellow, so their overlap stays visible.
RECTANGLE_ALPHA = {'Frame SELECT': .25, 'PAU': .85}
# 300 dpi renders the video at 2160 x 1680; the figure stays 7.2 x 5.6 in, so
# every size in points is unchanged. PX scales pixel offsets tuned at 150 dpi.
FPS, DPI = 25, 300
PX = DPI/150
# Image resolution of the SVG/PDF exports; their only raster content is the logos.
VECTOR_DPI = 600
MARKER_LANDING = .38
MARKER_CORNER_FRACTION = .18
SIZE = (2160, 1680)
# The GIF stays at the earlier size to keep its file small.
GIF_SIZE = (1080, 840)
OUT = HERE/'output'
STROKE_WIDTHS = {
    'axes': 1.3, 'major_ticks': 1.3, 'minor_ticks': 1.0,
    'released_cross': 2.5, 'markers': 2.1, 'filled_marker_edges': 1.2,
    'rectangles': 2.4, 'callout_boxes': 2.1, 'connectors': 2.1,
    'legend_border': 0,
}
LEGEND_LABELS = {
    'released': 'Released Frame SELECT [1]',
    'Frame SELECT': 'Frame SELECT [1]',
    'Frame extension': 'Frame SELECT + our optimizations',
    'PAU': 'Permute act unpermute [2]',
}
REFERENCES = [
    {'text': '[1] Gu et al., arXiv:2610.22367', 'url': 'https://arxiv.org/abs/2610.22367'},
    {'text': '[2] Summer & Jamet, arXiv:2610.03686', 'url': 'https://arxiv.org/abs/2610.03686'},
]
REFERENCE_NOTE = 'References identify the methods; the optimized points include additional work in this benchmark.'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clamp(x):
    return max(0, min(1, x))


def ease(x):
    return 1-(1-clamp(x))**3


def load_inputs():
    check_data()
    source = json.loads((HERE/'plot_data.json').read_text())
    return source


def schedule(source):
    keys = ['released', *SHOWN]
    groups = {k: sorted([r for r in source['rows'] if r['series'] == k],
                       key=lambda r: (r['q'],r['toffoli'],r['key'])) for k in keys}
    groups['released'] = [dict(source['baseline'],series='released')]
    timing=source['timing']
    return (groups,timing['starts'],timing['rectangle_start'],timing['finale'],
            timing['total'],timing['stages'])


def typography():
    fonts = HERE/'assets/fonts'
    for weight in ('Regular', 'Italic', 'Bold'):
        font_manager.fontManager.addfont(fonts/f'Rubik-{weight}.ttf')
    return {'font.family': 'Rubik', 'font.sans-serif': ['Rubik'], 'font.size': 11,
        'axes.labelsize': 12, 'xtick.labelsize': 10.5, 'ytick.labelsize': 10.5,
        'mathtext.fontset': 'custom', 'mathtext.fallback': None, 'mathtext.rm': 'Rubik',
        'mathtext.it': 'Rubik:style=italic', 'mathtext.bf': 'Rubik:weight=bold',
        'mathtext.bfit': 'Rubik:style=italic', 'mathtext.sf': 'Rubik',
        'mathtext.tt': 'Rubik', 'mathtext.cal': 'Rubik', 'svg.fonttype': 'none',
        'savefig.bbox': None, 'figure.facecolor': OFF_BLACK, 'axes.facecolor': OFF_BLACK,
        'savefig.facecolor': OFF_BLACK, 'text.color': WHITE, 'axes.labelcolor': WHITE,
        'axes.edgecolor': WHITE, 'xtick.color': WHITE, 'ytick.color': WHITE,
        'axes.linewidth': STROKE_WIDTHS['axes'],
        'xtick.major.width': STROKE_WIDTHS['major_ticks'],
        'ytick.major.width': STROKE_WIDTHS['major_ticks'],
        'xtick.minor.width': STROKE_WIDTHS['minor_ticks'],
        'ytick.minor.width': STROKE_WIDTHS['minor_ticks'],
        'lines.solid_capstyle': 'round', 'lines.solid_joinstyle': 'round',
        'lines.dash_capstyle': 'round', 'lines.dash_joinstyle': 'round'}


def rounded_marker(symbol):
    """Use the same curved polygon or round-ended stroke in plot and legend."""
    original = MarkerStyle(symbol,capstyle='round',joinstyle='round')
    if symbol not in ('s','D','^'):
        return original
    vertices = original.get_path().transformed(original.get_transform()).vertices[:-1]
    incoming = vertices+MARKER_CORNER_FRACTION*(np.roll(vertices,1,axis=0)-vertices)
    outgoing = vertices+MARKER_CORNER_FRACTION*(np.roll(vertices,-1,axis=0)-vertices)
    points,codes = [incoming[0]],[MplPath.MOVETO]
    for i,corner in enumerate(vertices):
        points.extend([corner,outgoing[i],incoming[(i+1)%len(vertices)]])
        codes.extend([MplPath.CURVE3,MplPath.CURVE3,MplPath.LINETO])
    points.append(incoming[0])
    codes.append(MplPath.CLOSEPOLY)
    # MarkerStyle normalizes custom paths. Restore the original symbol scale,
    # including the diamond's sqrt(2) larger bounding box.
    return MarkerStyle(MplPath(points,codes),capstyle='round',joinstyle='round',
        transform=Affine2D().scale(2*np.abs(vertices).max()))


def logo(filename, height, columns=None, checkerboard=False):
    pixels = plt.imread(HERE/'assets/logos'/filename).copy()
    if pixels.shape[2] == 3:
        pixels = np.dstack([pixels,np.ones(pixels.shape[:2])])
    if columns:
        pixels = pixels[:, slice(*columns)]
    if checkerboard:
        pixels[:, :, 3] = (pixels[:, :, :3].max(axis=2) < .65).astype(float)
    ys, xs = (pixels[:, :, 3] > 0).nonzero()
    pixels = pixels[ys.min():ys.max()+1, xs.min():xs.max()+1]
    # Pre-resample (Lanczos, premultiplied alpha) to the exact pixels the logo
    # covers at each output resolution, so matplotlib draws it one-to-one
    # instead of with its coarser downsampling.
    source = Image.fromarray((pixels*255).round().astype(np.uint8),'RGBA')
    resolutions = {}
    for kind,dpi in (('raster',DPI),('vector',VECTOR_DPI)):
        rows = round(height*dpi/72)
        columns = round(pixels.shape[1]*rows/pixels.shape[0])
        exact = source.convert('RGBa').resize((columns,rows),Image.Resampling.LANCZOS).convert('RGBA')
        resolutions[kind] = (np.asarray(exact)/255,72/dpi)
    data,zoom = resolutions['raster']
    image = OffsetImage(data,zoom=zoom)
    image.resolutions = resolutions
    return image


def logo_resolution(figure, kind):
    for image in figure.findobj(lambda artist: hasattr(artist,'resolutions')):
        data,zoom = image.resolutions[kind]
        image.set_data(data)
        image.set_zoom(zoom)


def fade_tree(artist, alpha):
    artist.set_alpha(alpha)
    for child in artist.get_children():
        fade_tree(child, alpha)


def prefix(vertices, fraction, transform):
    """Draw a fixed path progressively, using distance in display pixels."""
    vertices = np.asarray(vertices)
    lengths = np.linalg.norm(np.diff(transform.transform(vertices), axis=0), axis=1)
    target = lengths.sum()*clamp(fraction)
    result = [vertices[0]]
    for a,b,length in zip(vertices[:-1],vertices[1:],lengths):
        if target >= length:
            result.append(b)
            target -= length
        else:
            result.append(a+(b-a)*(target/length if length else 0))
            break
    return np.asarray(result).T


class Panel:
    def __init__(self, source):
        self.source = source
        self.groups, self.starts, self.red_start, self.finale, self.total, self.stages = schedule(source)
        self.fig = plt.figure(figsize=(SIZE[0]/DPI, SIZE[1]/DPI), dpi=DPI)
        self.ax = ax = self.fig.add_axes([.12, .17, .845, .785])
        ax.set(xlim=source['domains']['leftX'], ylim=source['domains']['leftY'],
            xlabel='Peak total logical qubits', ylabel='Toffoli count')
        ax.set_xticks([0,250,500,750,1000,1250], labels=['0','250','500','750','1,000','1,250'])
        ax.set_yticks([0,5000,10000,15000], labels=['0','5,000','10,000','15,000'])
        ax.tick_params(axis='both', pad=6)
        ax.spines[['top','right']].set_visible(False)
        for spine in ax.spines.values():
            spine.set_capstyle('round')
            spine.set_joinstyle('round')
        for axis in (ax.xaxis,ax.yaxis):
            for tick in [*axis.get_major_ticks(),*axis.get_minor_ticks()]:
                for line in (tick.tick1line,tick.tick2line):
                    line.set_marker(rounded_marker(line.get_marker()))
        ax.grid(False)
        self.reference_labels = []
        for x,reference in zip((.12,.55),REFERENCES):
            label = self.fig.text(x,.049,reference['text'],fontsize=8.0,
                ha='left',va='center',color=SECONDARY_INVERSE,url=reference['url'])
            self.reference_labels.append(label)
        self.reference_note = self.fig.text(.12,.018,REFERENCE_NOTE,fontsize=7.3,
            ha='left',va='center',color=SECONDARY_INVERSE,style='italic')
        self.fig.canvas.draw()
        self.marks = []
        for key, rows in self.groups.items():
            for order,row in enumerate(rows):
                if not row['panels']['toffoli']:
                    continue
                onset = row['onset_seconds']
                color = PAU_COLOR if key.startswith('PAU') else FRAME_COLOR
                if key == 'released':
                    artist = [ax.plot([],[],color=color,lw=STROKE_WIDTHS['released_cross'],solid_capstyle='round',zorder=6)[0] for _ in range(2)]
                    size = 0
                else:
                    filled = key in FILLED
                    # Filled diamonds lack the hollow markers' 2.1-pt stroke, so they are
                    # slightly larger, yet small enough for a coincident outline to show.
                    size = 52 if filled else 43
                    artist = ax.scatter([row['q']],[row['toffoli']],s=size,marker=rounded_marker(MARKERS[key]),
                        facecolors=color if filled else 'none',edgecolors=OFF_BLACK if filled else color,
                        lw=STROKE_WIDTHS['filled_marker_edges' if filled else 'markers'],zorder=5)
                    artist.set_capstyle('round')
                    artist.set_joinstyle('round')
                    artist.set_gid('point-'+row['key'])
                self.marks.append((artist,row,key,onset,size))
        self.areas = []
        for row,color,alpha,start in [(source['baseline'],FRAME_COLOR,RECTANGLE_ALPHA['Frame SELECT'],self.starts['released']+MARKER_LANDING),
                                      (source['best'],PAU_COLOR,RECTANGLE_ALPHA['PAU'],self.red_start)]:
            q,t = row['q'], row['toffoli']
            fill = Rectangle((q,t),0,0,facecolor=color,alpha=alpha,edgecolor='none',zorder=1.1 if color == FRAME_COLOR else 1)
            ax.add_patch(fill)
            paths = [np.array([[q,t],[0,t],[0,0]]),np.array([[q,t],[q,0],[0,0]])]
            lines = [ax.plot([],[],color=color,lw=STROKE_WIDTHS['rectangles'],zorder=2)[0] for _ in paths]
            self.areas.append((row,fill,paths,lines,start))
        handles = [Line2D([],[],color=FRAME_COLOR,marker=rounded_marker('x'),linestyle='none',markersize=7,markeredgewidth=STROKE_WIDTHS['released_cross'])]
        for key,marker in MARKERS.items():
            color = PAU_COLOR if key.startswith('PAU') else FRAME_COLOR
            filled = key in FILLED
            handles.append(Line2D([],[],color=color,marker=rounded_marker(marker),linestyle='none',
                markersize=6.9 if filled else 6.3,markerfacecolor=color if filled else 'none',markeredgecolor=OFF_BLACK if filled else color,
                markeredgewidth=STROKE_WIDTHS['filled_marker_edges' if filled else 'markers']))
        self.legend = ax.legend(handles,list(LEGEND_LABELS.values()),loc='lower right',fontsize=8.0,
            labelspacing=.12,borderpad=.4,handletextpad=.65,borderaxespad=.3,
            facecolor=CARD_DARK,edgecolor='none',framealpha=1,fancybox=True)
        self.legend.get_frame().set_linewidth(STROKE_WIDTHS['legend_border'])
        self.legend.get_frame().set_boxstyle('round',pad=0,rounding_size=1.0)
        self.legend.get_frame().set_capstyle('round')
        self.legend.get_frame().set_joinstyle('round')
        self.calls = []
        frame_logos = HPacker(children=[logo('anthropic-icon-supplied.png',20,checkerboard=True),
            TextArea('+',textprops={'fontsize':17,'color':FRAME_COLOR}),logo('quera.png',20,(78,367))],align='center',pad=0,sep=7)
        # White cards outlined in each method's colour: salmon for the
        # release, yellow for permute act unpermute. White keeps the logos legible.
        for row,color,fill,edge,marks,cy in [(source['baseline'],FRAME_COLOR,WHITE,FRAME_COLOR,frame_logos,.87),
                                  (source['best'],PAU_COLOR,WHITE,PAU_COLOR,logo('alice-bob-icon-supplied.png',27),.635)]:
            left,right,bottom,top = .53,.94,cy-.085,cy+.085
            rx,ry = 18*PX/ax.bbox.width,18*PX/ax.bbox.height
            points = []
            for cx,yy,angles in [(right-rx,top-ry,(0,90)),(left+rx,top-ry,(90,180)),
                                (left+rx,bottom+ry,(180,270)),(right-rx,bottom+ry,(270,360))]:
                angle = np.deg2rad(np.linspace(*angles,12))
                points.extend(np.c_[cx+rx*np.cos(angle),yy+ry*np.sin(angle)])
            points.append(points[0])
            vertices = np.array(points)
            bg = Polygon(vertices,closed=True,facecolor=fill,edgecolor='none',alpha=0,transform=ax.transAxes,zorder=7)
            ax.add_patch(bg)
            outline, = ax.plot([],[],color=edge,lw=STROKE_WIDTHS['callout_boxes'],transform=ax.transAxes,zorder=8)
            anchor = ax.transAxes.inverted().transform(ax.transData.transform([row['q'],row['toffoli']]))
            connector = np.array([anchor+[.009,.004],[left-.012,cy-(.045 if color == PAU_COLOR else .012)]])
            line, = ax.plot([],[],color=color,lw=STROKE_WIDTHS['connectors'],transform=ax.transAxes,zorder=3)
            marks_box = AnnotationBbox(marks,(.735,cy+.024),xycoords=ax.transAxes,frameon=False,pad=0,zorder=9)
            ax.add_artist(marks_box)
            label = ax.text(.735,cy-.047,rf'$\mathrm{{TQ}}_{{\mathrm{{peak}}}} = \mathbf{{'+f"{row['tq']:,}".replace(',',r'{,}')+'}$',
                ha='center',va='center',color=OFF_BLACK,
                fontsize=11.5,transform=ax.transAxes,zorder=9)
            self.calls.append((bg,outline,vertices,line,connector,marks_box,label,cy))

    def draw(self, time):
        ax = self.ax
        inv = ax.transData.inverted()
        for artist,row,key,onset,size in self.marks:
            a = ease((time-onset)/MARKER_LANDING)
            center = ax.transData.transform([row['q'],row['toffoli']])+[0,-(1-a)*7*PX]
            if key == 'released':
                half = 7*PX*(.45+.55*a)
                for i,line in enumerate(artist):
                    start = center+[-half,(-1 if i == 0 else 1)*half]
                    end = center+[half,(1 if i == 0 else -1)*half]
                    stroke = clamp((time-onset-i*.09)/.25)
                    line.set_data(inv.transform([start,start+(end-start)*stroke]).T)
                    line.set_alpha(a)
            else:
                artist.set_offsets([inv.transform(center)])
                artist.set_sizes([size*(.45+.55*a)**2])
                artist.set_alpha(a)
        for row,fill,paths,lines,start in self.areas:
            a,f = ease((time-start)/.82),ease((time-start-.12)/.82)
            q,t = row['q'],row['toffoli']
            fill.set_bounds(q*(1-f),t*(1-f),q*f,t*f)
            for path,line in zip(paths,lines):
                line.set_data(prefix(path,a,ax.transData))
                line.set_visible(a > 0)
        for key,handle,label in zip(self.groups,self.legend.legend_handles,self.legend.get_texts()):
            a = ease((time-self.starts[key])/.3)
            handle.set_alpha(a)
            label.set_alpha(a)
        self.legend.get_frame().set_alpha(ease((time-.2)/.3))
        for bg,outline,vertices,line,connector,marks,label,cy in self.calls:
            a = ease((time-self.finale)/.42)
            l = ease((time-self.finale-.2)/.4)
            v = ease((time-self.finale-.6)/.45)
            bg.set_alpha(l)
            outline.set_data(prefix(vertices,a,ax.transAxes))
            line.set_data(prefix(connector,a,ax.transAxes))
            outline.set_visible(a > 0)
            line.set_visible(a > 0)
            fade_tree(marks,l)
            marks.xy = (.735,cy+.024-(1-l)*6*PX/ax.bbox.height)
            label.set_alpha(v)
            label.set_y(cy-.047-(1-v)*5*PX/ax.bbox.height)
        self.fig.canvas.draw()

    def image(self):
        return Image.fromarray(np.asarray(self.fig.canvas.buffer_rgba())[:,:,:3].copy())

    def check_rectangle_landings(self):
        for row,fill,paths,lines,start in self.areas:
            artist,marker,key,onset,size = next(m for m in self.marks if m[1]['key'] == row['key'])
            assert abs(start-onset-MARKER_LANDING) < 1e-12
            self.draw(start-1e-6)
            assert all(not line.get_visible() for line in lines)
            assert fill.get_width() == fill.get_height() == 0
            self.draw(start)
            if key != 'released':
                assert np.allclose(artist.get_offsets()[0],[row['q'],row['toffoli']],rtol=0,atol=1e-10)
            self.draw(start+.08)
            for line in lines:
                assert np.array_equal(np.array(line.get_data())[:,0],[row['q'],row['toffoli']])
            self.draw(start+.2)
            assert np.allclose([fill.get_x()+fill.get_width(),fill.get_y()+fill.get_height()],
                [row['q'],row['toffoli']],rtol=0,atol=1e-10)

    def check_final(self):
        self.draw(self.total)
        for text in self.fig.findobj(match=Text):
            font = Path(font_manager.findfont(text.get_fontproperties(),fallback_to_default=False))
            assert font.name.startswith('Rubik-'), (text.get_text(),str(font))
        for artist,row,key,onset,size in self.marks:
            if key != 'released':
                assert np.allclose(artist.get_offsets()[0],[row['q'],row['toffoli']],rtol=0,atol=1e-10)
                assert artist.get_capstyle() == artist.get_joinstyle() == 'round'
                if MARKERS[key] in ('s','D','^'):
                    assert MplPath.CURVE3 in artist.get_paths()[0].codes
        for line in self.ax.lines:
            assert line.get_solid_capstyle() == line.get_solid_joinstyle() == 'round'
        for row,fill,*_ in self.areas:
            assert fill.get_x() == fill.get_y() == 0
            assert fill.get_width()*fill.get_height() == row['tq']
        legend_bounds = self.legend.get_window_extent(self.fig.canvas.get_renderer())
        for artist,row,*_ in self.marks:
            assert not legend_bounds.padded(9*PX).contains(*self.ax.transData.transform([row['q'],row['toffoli']]))
        assert [label.get_text() for label in self.legend.get_texts()] == list(LEGEND_LABELS.values())
        renderer = self.fig.canvas.get_renderer()
        footer_bounds = [label.get_window_extent(renderer) for label in [*self.reference_labels,self.reference_note]]
        for bounds in footer_bounds:
            assert bounds.x0 >= 0 and bounds.y0 >= 0 and bounds.x1 <= SIZE[0]
            assert bounds.y1 < self.ax.xaxis.label.get_window_extent(renderer).y0
        for i,bounds in enumerate(footer_bounds):
            assert all(not bounds.overlaps(other) for other in footer_bounds[i+1:])
        assert self.image().size == SIZE


def encode(frames, output, fps, requested):
    use_swift = requested == 'swift' or (requested == 'auto' and platform.system() == 'Darwin' and shutil.which('swift'))
    if use_swift:
        compiler = shutil.which('swift')
        if not compiler:
            raise RuntimeError('Swift is unavailable; install it or use --encoder ffmpeg.')
        with tempfile.TemporaryDirectory(prefix='fe2s2-swift-cache-') as cache:
            subprocess.run([compiler,'-module-cache-path',cache,str(HERE/'encode_panel_video.swift'),
                            str(frames),str(output),str(fps)],check=True)
        return 'swift-avfoundation'
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('MP4 encoding needs Swift on macOS or ffmpeg with libx264; use --gif-only for GIF output.')
    subprocess.run([ffmpeg,'-y','-loglevel','error','-framerate',str(fps),'-i',str(frames/'%04d.png'),
                    '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],check=True)
    return 'ffmpeg-libx264'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-only',action='store_true',help='Render only the final PNG, SVG and PDF.')
    parser.add_argument('--gif-only',action='store_true',help='Render GIF without an external MP4 encoder.')
    parser.add_argument('--encoder',choices=['auto','swift','ffmpeg'],default='auto')
    parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args()
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    source=load_inputs()
    with plt.style.context(HERE/'plot.mplstyle'),matplotlib.rc_context(typography()):
        panel=Panel(source)
        panel.check_rectangle_landings()
        panel.check_final()
        description=source['boundary']+' Native Toffoli count versus peak total logical qubits. '+source['validation_scope']
        outputs=[]
        for ext in ('png','svg','pdf'):
            metadata={'Title':'Fe2S2 resource tradeoffs, compact panel (a)',
                      'Subject' if ext=='pdf' else 'Description':description}
            logo_resolution(panel.fig,'raster' if ext=='png' else 'vector')
            path=out/f'fe2s2_panel_a_compact.{ext}'
            panel.fig.savefig(path,dpi=DPI if ext=='png' else VECTOR_DPI,metadata=metadata)
            outputs.append(path)
        logo_resolution(panel.fig,'raster')
        duration=math.ceil((panel.total+2.5)*FPS)/FPS
        encoder=None
        if not args.preview_only:
            frame_count=round(duration*FPS)
            gif_frame=lambda frame: frame.resize(GIF_SIZE,Image.Resampling.LANCZOS)
            palette=gif_frame(panel.image()).quantize(colors=256,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
            gif_frames=[]
            with tempfile.TemporaryDirectory(prefix='fe2s2-frames-') as directory:
                frames=Path(directory)
                for i in range(frame_count):
                    panel.draw(min(i/FPS,panel.total))
                    frame=panel.image()
                    if not args.gif_only:
                        frame.save(frames/f'{i:04d}.png',compress_level=1)
                    if i%2==0:
                        gif_frames.append(gif_frame(frame).quantize(palette=palette,dither=Image.Dither.NONE))
                    if i%FPS==0:
                        print(f'Rendered {i/FPS:.0f}/{duration:.2f} seconds',flush=True)
                gif_path=out/'fe2s2_panel_a_animated.gif'
                gif_frames[0].save(gif_path,save_all=True,append_images=gif_frames[1:],loop=0,
                                   duration=80,disposal=1,optimize=True)
                outputs.append(gif_path)
                if not args.gif_only:
                    mp4=out/'fe2s2_panel_a_animated.mp4'
                    encoder=encode(frames,mp4,FPS,args.encoder)
                    outputs.append(mp4)
            panel.check_final()
            with Image.open(gif_path) as gif:
                gif_duration=0
                for i in range(gif.n_frames):
                    gif.seek(i)
                    gif_duration+=gif.info['duration']/1000
                assert abs(gif_duration-duration)<.081
                assert gif.size==GIF_SIZE
                reference=gif_frame(panel.image()).quantize(palette=palette,dither=Image.Dither.NONE).convert('RGB')
                assert np.array_equal(np.asarray(gif.convert('RGB')),np.asarray(reference))
        record=dict(schema_version=1,status='PRESENTATION_EXPORT_VERIFIED',
            plot_data_sha256=sha(HERE/'plot_data.json'),generator_sha256=sha(Path(__file__)),
            boundary=source['boundary'],validation_scope=source['validation_scope'],
            baseline=source['baseline'],best_pau=source['best'],visible_points=source['rows'],
            encoder=encoder,video_duration_seconds=duration,video_fps=FPS,
            pixel_dimensions=list(SIZE),gif_pixel_dimensions=list(GIF_SIZE),
            preview_only=args.preview_only,gif_only=args.gif_only,
            checks=['circuit manifest linkage','exact rectangle areas','point landing alignment',
                    'final coordinates','legend clearance','reference placement','Rubik text'],
            output_sha256={p.name:sha(p) for p in outputs})
        (out/'render_report.json').write_text(json.dumps(record,indent=2)+'\n')
        plt.close(panel.fig)
        print(json.dumps({'outputs':record['output_sha256'],'duration':duration,'size':SIZE},indent=2))


if __name__ == '__main__':
    main()
