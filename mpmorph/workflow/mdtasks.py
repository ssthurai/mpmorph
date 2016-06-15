from fireworks import explicit_serialize, FireTaskBase, FWAction, Firework
from mpmorph.runners.amorphous_maker import AmorphousMaker
from mpmorph.runners.rescale_volume import RescaleVolume
from mpmorph.analysis.md_data import parse_pressure
from matmethods.vasp.firetasks.glue_tasks import CopyVaspOutputs
from matmethods.vasp.firetasks.run_calc import RunVaspCustodian
from matmethods.common.firetasks.glue_tasks import PassCalcLocs
from matmethods.vasp.firetasks.parse_outputs import VaspToDbTask

__author__ = 'Muratahan Aykol <maykol@lbl.gov>'


@explicit_serialize
class AmorphousMakerTask(FireTaskBase):
    """
    Create a constraint random packed structure from composition and box dimensions.
    Required params:
        composition: (dict) a dict of target composition with integer atom numbers
                        e.g. {"V":22, "Li":10, "O":75, "B":10}
        box_scale: (float) all lattice vectors are multiplied with this scalar value.
                        e.g. edge length of a cubic simulation box.
    Optional params:
        tol (float): tolerance factor for how close the atoms can get (angstroms).
                        e.g. tol = 2.0 angstroms
        packmol_path (str): path to the packmol executable. Defaults to "packmol"
        clean (bool): whether the intermedite files generated are deleted. Defaults to True.
    """

    required_params = ["composition", "box_scale"]
    optional_params = ["packmol_path", "clean", "tol"]

    def run_task(self, fw_spec):
        glass = AmorphousMaker(self.get("composition"), self.get("box_scale"), self.get("tol", 2.0),
                               packmol_path=self.get("packmol_path", "packmol"),
                               clean=self.get("clean", True))
        structure = glass.random_packed_structure
        return FWAction(stored_data=structure)


@explicit_serialize
class GetPressureTask(FireTaskBase):
    required_params = ["outcar_path"]
    optional_params = ["averaging_fraction"]

    def run_task(self, fw_spec):
        p = parse_pressure(self["outcar_path"], self.get("averaging_fraction", 0.5))
        return FWAction(stored_data={'avg_pres': p[0] * 1000})


@explicit_serialize
class SpawnMDFWTask(FireTaskBase):
    required_params = ["pressure_threshold", "vasp_cmd", "wall_time", "db_file"]

    def run_task(self, fw_spec):
        vasp_cmd = self["vasp_cmd"]
        wall_time = self["wall_time"]
        db_file = self["db_file"]
        parents = fw_spec["parents"]

        t = []
        t.append(CopyVaspOutputs(calc_loc=True, contcar_to_poscar=True,
                                 additional_files=["CHGCAR"]))
        t.append(RescaleVolumeTask(initial_pressure=avg_pres, initial_temperature=1))
        t.append(RunVaspCustodian(vasp_cmd=vasp_cmd, gamma_vasp_cmd=">>gamma_vasp_cmd<<",
                                  handler_group="md", wall_time=wall_time))
        t.append(PassCalcLocs(name="density_adjustment"))
        t.append(VaspToDbTask(db_file=db_file,
                              additional_fields={"task_label": "density_adjustment"}))
        t.append(GetPressureTask(outcar_path="./OUTCAR"))

        if avg_pres > self["pressure_threshold"]:
            new_fw = Firework(t, parents=parents.extend(t))
        else:
            return FWAction(stored_data={'pressure': avg_pres, 'density_calculated': True})
        return FWAction(stored_data={'pressure': avg_pres}, additions=[new_fw])


@explicit_serialize
class RescaleVolumeTask(FireTaskBase):
    """
    Volume rescaling
    """
    required_params = ["initial_temperature", "initial_pressure"]
    optional_params = ["target_pressure", "target_temperature", "target_pressure", "alpha", "beta"]

    def run_task(self, fw_spec):
        # Initialize volume correction object with last structure from last_run
        initial_temperature = self["initial_temperature"]
        initial_pressure = self["initial_pressure"]
        target_temperature = self.get("target_temperature", initial_temperature)
        target_pressure = self.get("target_pressure", 0.0)
        alpha = self.get("alpha", 10e-6)
        beta = self.get("beta", 10e-7)
        corr_vol = RescaleVolume.of_poscar(poscar_path="./POSCAR", initial_temperature=initial_temperature,
                                           initial_pressure=initial_pressure,
                                           target_pressure=target_pressure,
                                           target_temperature=target_temperature, alpha=alpha, beta=beta)
        # Rescale volume based on temperature difference first. Const T will return no volume change:
        corr_vol.by_thermo(scale='temperature')
        # TO DB ("Rescaled volume due to delta T: ", corr_vol.structure.volume)
        # Rescale volume based on pressure difference:
        corr_vol.by_thermo(scale='pressure')
        # TO DB ("Rescaled volume due to delta P: ", corr_vol.structure.volume)
        corr_vol.poscar.write_file("./POSCAR")
        # Pass the rescaled volume to Poscar
        return FWAction(stored_data=corr_vol.structure.as_dict())


@explicit_serialize
class DecideNextRunTypeTask(FireTaskBase):
    """
    Decides whether
    """
    pass

@explicit_serialize
class VaspMdToDbTask(FireTaskBase):
    pass


@explicit_serialize
class VaspMdToDiffusion(FireTaskBase):
    pass


@explicit_serialize
class VaspMdToStructuralAnalysis(FireTaskBase):
    pass