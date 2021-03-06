from fireworks import Workflow, Firework
from atomate.vasp.fireworks.core import MDFW, OptimizeFW, StaticFW
from mpmorph.workflow.mdtasks import SpawnMDFWTask, CopyCalsHome
from mpmorph.runners.amorphous_maker import AmorphousMaker
from mpmorph.analysis.structural_analysis import get_sample_structures
from atomate.vasp.firetasks.glue_tasks import CopyVaspOutputs
from pymatgen.core.structure import Structure
import os


def get_wf_density(structure, temperature, pressure_threshold=5.0, max_rescales=6, nsteps=2000, wall_time=19200,
                   vasp_input_set=None, vasp_cmd=">>vasp_cmd<<", db_file=">>db_file<<", name="density_finder",
                   optional_MDWF_params=None, override_default_vasp_params=None,
                   amorphous_maker_params=None, copy_calcs=False, calc_home="~/wflows"):
    """
    :param structure: (
    :param temperature:
    :param pressure_threshold:
    :param max_rescales:
    :param nsteps:
    :param wall_time:
    :param vasp_input_set:
    :param vasp_cmd:
    :param db_file:
    :param name:
    :param optional_MDWF_params:
    :param override_default_vasp_params:
    :param amorphous_maker_params:
    :param copy_calcs:
    :param calc_home:
    :return:
    """
    if copy_calcs:
        if not os.path.exists(calc_home):
            raise ValueError("calc_home must be an existing folder.")
        elif os.path.exists(calc_home+"/"+name):
            raise ValueError("WF name already exists, choose a different name.")
        else:
            calc_home = os.path.join(calc_home,name)
            os.mkdir(calc_home)

    # If structure is in fact just a composition, create a random packed Structure!
    if not isinstance(structure, Structure) and isinstance(structure, dict):
        if not amorphous_maker_params:
            raise ValueError("amorphous_maker_params must be defined!")
        glass = AmorphousMaker(structure, **amorphous_maker_params)
        structure = glass.random_packed_structure

    optional_MDWF_params = optional_MDWF_params or {}
    override_default_vasp_params = override_default_vasp_params or {}
    override_default_vasp_params['user_incar_settings'] = override_default_vasp_params.get('user_incar_settings') or {}
    override_default_vasp_params['user_incar_settings'].update({"ISIF": 1, "LWAVE": False})

    fw1 = MDFW(structure=structure, start_temp=temperature, end_temp=temperature, nsteps=nsteps,
               name=name+"run0", vasp_input_set=vasp_input_set, db_file=db_file,
               vasp_cmd=vasp_cmd, wall_time=wall_time, override_default_vasp_params=override_default_vasp_params,
               **optional_MDWF_params)
    t = [CopyVaspOutputs(calc_loc=True, contcar_to_poscar=True, additional_files =["XDATCAR", "OSZICAR", "DOSCAR"])]

    if copy_calcs:
         t.append(CopyCalsHome(calc_home=calc_home, run_name="run0"))
    t.append(SpawnMDFWTask(pressure_threshold=pressure_threshold, max_rescales=max_rescales,
                       wall_time=wall_time, vasp_cmd=vasp_cmd, db_file=db_file,
                       copy_calcs=copy_calcs, calc_home=calc_home,
                       spawn_count=0))

    fw2 = Firework(t, parents=[fw1], name=name+"_initial_spawn")
    return Workflow([fw1, fw2], name=name+"_WF")


def get_wf_structure_sampler(xdatcar_file, n=10, steps_skip_first=1000, vasp_cmd=">>vasp_cmd<<",
                             db_file=">>db_file<<", name="structure_sampler", **kwargs):
    """
    :param xdatcar_file:
    :param n:
    :param steps_skip_first:
    :param vasp_cmd:
    :param db_file:
    :param name:
    :param kwargs:
    :return:
    """
    structures = get_sample_structures(xdatcar_path=xdatcar_file, n=n, steps_skip_first=steps_skip_first)
    wfs = []
    for s in structures:
        fw1=OptimizeFW(s, vasp_cmd=vasp_cmd, db_file=db_file, parents=[], **kwargs)
        fw2=StaticFW(s, vasp_cmd=vasp_cmd, db_file=db_file, parents=[fw1])
        wfs.append(Workflow([fw1,fw2], name=name+str(s.composition.reduced_formula)) )
    return wfs


def get_relax_static_wf(structures, vasp_cmd=">>vasp_cmd<<", db_file=">>db_file<<", name="regular_relax", **kwargs):
    """
    :param structures:
    :param vasp_cmd:
    :param db_file:
    :param name:
    :param kwargs:
    :return:
    """
    wfs = []
    for s in structures:
        fw1=OptimizeFW(s, vasp_cmd=vasp_cmd, db_file=db_file, parents=[], **kwargs)
        fw2=StaticFW(s, vasp_cmd=vasp_cmd, db_file=db_file, parents=[fw1])
        wfs.append(Workflow([fw1,fw2], name=name+str(s.composition.reduced_formula)) )
    return wfs
