"""System cores, with decoded labels at the boundary and no data lookup.

The two-family core below is the system-action portion of joint_select,
including its affine projections and their cleanup. Scalar phases already
factored into the label lookup are outside these PAU core boundaries.
"""
from functools import lru_cache
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'shared'),str(ROOT/'upstream')]


@lru_cache(None)
def two_data():
    import compact_families as cf
    import family_pau as fp
    spec=cf.pooled_layout('spin_split',True,'high',0)
    old=fp.layout;fp.layout=lambda *args:spec;fp.data.cache_clear()
    try:table=fp.data('spin_split',True,'high',0,'joint',1)[0]
    finally:fp.layout=old;fp.data.cache_clear()
    return spec,table


def widths(kind):
    if kind=='single':return dict(flags=7,label=29,system=40)
    if kind=='two':return dict(flags=7,label=len(two_data()[1][2]),system=40)
    if kind=='frame':
        from frame_mask_space import table
        return dict(index=16,flags=7,label=len(table()[2]),system=40)
    raise ValueError(kind)


def emit(kind,b,regs):
    flags,label,x=(regs[k] for k in ('flags','label','system'))
    if kind=='single':
        from phase_pau import phase_free_core
        return phase_free_core(b,flags,label,x)
    if kind=='frame':
        from multiframe import conjugate
        from frame_mask_space import act
        conjugate(b,flags,x)
        act(b,regs['index'],label,x)
        conjugate(b,flags,x,inverse=True)
        return
    import compact_families as cf
    import family_pau as fp
    from reuse_family_core import reuse
    from basis_action_controls import use
    spec,table=two_data()
    with reuse(b), use(dict(scheme='spin_split',shared_pair=True,padding='high',partition=0,pooled_actions=True)):
        views=cf.AffineViews(b)
        def projection(part):
            shift=sum(spec['widths'][:part]);width=spec['widths'][part]
            _,_,basis,constant,_=table
            return views.acquire([(tuple(c for c,v in zip(label,basis) if v>>(shift+j)&1),constant>>(shift+j)&1) for j in range(width)])
        glob,close_global=projection(0)
        shared_run,shared_close=cf.shared_prefix(b,flags,glob,x)
        shared_run()
        for number,branch in enumerate(spec['branches'],1):
            local,close=projection(number)
            run,end=cf.quantum_route(b,local,x,fp.stages(branch['kind'],branch['shared']))
            run();cf.enabled_action(b,flags,local,x,branch,glob[spec['enable_offset']+number-1])
            run(True);end();close()
        shared_run(True);shared_close();close_global()
