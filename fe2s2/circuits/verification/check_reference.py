#!/usr/bin/env python3
"""Independent Pauli, coefficient-sign and integer-alias distribution checks."""
import hashlib,json,lzma,math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import circuits


def check():
    words,masks=circuits.reference_data()
    data=ROOT/'upstream/tasks/chemistry-fe2s2/data/table.json.xz'
    table=json.loads(lzma.decompress(data.read_bytes()));terms=table['terms'];L=len(terms);scale=65536
    weights=[];mass=[0]*L;coeffs=[]
    for i,(t,word,mask) in enumerate(zip(terms,words,masks)):
        flip=zy=ys=0
        for token in t['pauli'].split():
            op=token[0];q=int(token[1:]);assert 0<=q<40 and op in 'XYZ'
            if op in 'XY':flip|=1<<q
            if op in 'YZ':zy|=1<<q
            ys+=op=='Y'
        assert ys%2==0
        assert mask==flip|(zy<<40)|(((ys//2)%2)<<80)
        coeff=float.fromhex(t['coeff']);coeffs.append(coeff)
        assert abs(coeff)>=float(table['truncation_threshold']) and (flip or zy)
        assert (word>>33)&1==int(coeff<0)
        keep=word&65535;alt=(word>>16)&65535
        assert 0<=alt<L and t['keep']==keep and t['alt']==alt and t['i']==i
        assert (word>>32)&1==(words[alt]>>33)&1
        mass[i]+=keep;mass[alt]+=scale-keep;weights.append(t['m'])
    assert sum(mass)==L*scale and mass==weights
    alpha=math.fsum(map(abs,coeffs));assert alpha==float(table['lambda'])
    targets=[abs(c)/alpha*L*scale for c in coeffs];rounded=[math.floor(v) for v in targets]
    remainder=L*scale-sum(rounded)
    for i in sorted(range(L),key=lambda i:(-(targets[i]-rounded[i]),i))[:remainder]:rounded[i]+=1
    assert rounded==weights
    l1=sum(abs(m/(L*scale)-abs(c)/alpha) for m,c in zip(mass,coeffs))
    return dict(status='PASS',rows=L,alias_precision=16,normalization=alpha,
                exact_integer_mass=L*scale,probability_l1_error=l1,
                scope='Every stored Pauli, sign, alias mass and largest-remainder weight; FCIDUMP-to-Pauli derivation is a separate upstream check.',
                table_sha256=hashlib.sha256(data.read_bytes()).hexdigest())


if __name__=='__main__':print(json.dumps(check(),indent=2))
