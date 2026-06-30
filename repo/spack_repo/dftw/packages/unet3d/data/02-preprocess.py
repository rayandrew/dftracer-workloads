# Taken from https://github.com/mlcommons/training/blob/master/retired_benchmarks/unet3d/pytorch/preprocess_dataset.py

import argparse
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor

import nibabel
import numpy as np
from scipy.ndimage import zoom
from tqdm import tqdm

EXCLUDED_CASES = []  # [23, 68, 125, 133, 15, 37]
MAX_ID = 210
MEAN_VAL = 101.0
STDDEV_VAL = 76.9
MIN_CLIP_VAL = -79.0
MAX_CLIP_VAL = 304.0
TARGET_SPACING = [1.6, 1.2, 1.2]
TARGET_SHAPE = [128, 128, 128]


class Stats:
    def __init__(self):
        self.mean = []
        self.std = []
        self.d = []
        self.h = []
        self.w = []

    def append(self, mean, std, d, h, w):
        self.mean.append(mean)
        self.std.append(std)
        self.d.append(d)
        self.h.append(h)
        self.w.append(w)

    def get_string(self):
        self.mean = np.median(np.array(self.mean))
        self.std = np.median(np.array(self.std))
        self.d = np.median(np.array(self.d))
        self.h = np.median(np.array(self.h))
        self.w = np.median(np.array(self.w))
        return f"Mean value: {self.mean}, std: {self.std}, d: {self.d}, h: {self.h}, w: {self.w}"


class Preprocessor:
    def __init__(self, args):
        self.mean = MEAN_VAL
        self.std = STDDEV_VAL
        self.min_val = MIN_CLIP_VAL
        self.max_val = MAX_CLIP_VAL
        self.results_dir = args.results_dir
        self.data_dir = args.data_dir
        self.target_spacing = TARGET_SPACING
        self.jobs = args.jobs
        self.stats = Stats()

    def _pending(self):
        """Cases needing work: present in the source, not yet fully written (resume)."""
        out = []
        for case in sorted(f for f in os.listdir(self.data_dir) if "case" in f):
            case_id = int(case.split("_")[1])
            if case_id in EXCLUDED_CASES or case_id >= MAX_ID:
                continue
            if os.path.exists(os.path.join(self.results_dir, f"{case}_x.npz")):
                continue
            out.append(case)
        return out

    def preprocess_dataset(self):
        os.makedirs(self.results_dir, exist_ok=True)
        pending = self._pending()
        print(f"Preprocessing {self.data_dir}: {len(pending)} cases, {self.jobs} workers")
        with ProcessPoolExecutor(max_workers=self.jobs) as ex:
            for st in tqdm(ex.map(self.process_one, pending), total=len(pending)):
                if st is not None:
                    self.stats.append(*st)
        if self.stats.mean:
            print(self.stats.get_string())
        with open(os.path.join(self.results_dir, ".preprocessed"), "w") as f:
            f.write("ok\n")

    def process_one(self, case):
        image, label, image_spacings = self.load_pair(case)
        image, label = self.preprocess_case(image, label, image_spacings)
        image, label = self.pad_to_min_shape(image, label)
        return self.save(image, label, case)

    def preprocess_case(self, image, label, image_spacings):
        image, label = self.resample3d(image, label, image_spacings)
        image = self.normalize_intensity(image.copy())
        return image, label

    @staticmethod
    def pad_to_min_shape(image, label):
        current_shape = image.shape[1:]
        bounds = [max(0, TARGET_SHAPE[i] - current_shape[i]) for i in range(3)]
        paddings = [(0, 0)]
        paddings.extend([(bounds[i] // 2, bounds[i] - bounds[i] // 2) for i in range(3)])
        return np.pad(image, paddings, mode="edge"), np.pad(label, paddings, mode="edge")

    def load_pair(self, case: str):
        image = nibabel.load(os.path.join(self.data_dir, case, "imaging.nii.gz"))
        label = nibabel.load(os.path.join(self.data_dir, case, "segmentation.nii.gz"))

        image_spacings = image.header["pixdim"][1:4].tolist()
        image, label = image.get_fdata().astype(np.float32), label.get_fdata().astype(np.uint8)
        image, label = np.expand_dims(image, 0), np.expand_dims(label, 0)
        return image, label, image_spacings

    def resample3d(self, image, label, image_spacings):
        if image_spacings != self.target_spacing:
            spc_arr = np.array(image_spacings)
            targ_arr = np.array(self.target_spacing)
            shp_arr = np.array(image.shape[1:])
            new_shape = (spc_arr / targ_arr * shp_arr).astype(int).tolist()

            factors = [1.0] + [n / o for n, o in zip(new_shape, image.shape[1:])]
            image = zoom(image, factors, order=1, grid_mode=False)
            label = zoom(label, factors, order=0, grid_mode=False)
        return image, label

    def normalize_intensity(self, image: np.array):
        image = np.clip(image, self.min_val, self.max_val)
        image = (image - self.mean) / self.std
        return image

    def _atomic_savez(self, stem: str, arr):
        """Write {stem}.npz via temp + rename so a killed run never leaves a partial
        file that the resume check would mistake for complete."""
        final = os.path.join(self.results_dir, f"{stem}.npz")
        tmp = os.path.join(self.results_dir, f".{stem}.partial.npz")
        np.savez(tmp, data=arr)
        os.replace(tmp, final)

    def save(self, image, label, case: str):
        image = image.astype(np.float32)
        label = label.astype(np.uint8)
        mean, std = np.round(np.mean(image, (1, 2, 3)), 2), np.round(np.std(image, (1, 2, 3)), 2)
        self._atomic_savez(f"{case}_y", label)
        self._atomic_savez(f"{case}_x", image)
        return (mean, std, image.shape[1], image.shape[2], image.shape[3])


def verify_dataset(results_dir):
    with open("checksum.json") as f:
        source = json.load(f)

    assert len(source) == len(os.listdir(results_dir))
    for volume in tqdm(os.listdir(results_dir)):
        with open(os.path.join(results_dir, volume), "rb") as f:
            data = f.read()
            md5_hash = hashlib.md5(data).hexdigest()
            assert md5_hash == source[volume], f"Invalid hash for {volume}."
    print("Verification completed. All files' checksums are correct.")


if __name__ == "__main__":
    PARSER = argparse.ArgumentParser()
    PARSER.add_argument("--data_dir", dest="data_dir", required=True)
    PARSER.add_argument("--results_dir", dest="results_dir", required=True)
    PARSER.add_argument(
        "--mode", dest="mode", choices=["preprocess", "verify"], default="preprocess"
    )
    PARSER.add_argument(
        "--jobs",
        type=int,
        default=int(os.environ.get("DFTW_PREP_JOBS") or min(8, os.cpu_count() or 1)),
        help="parallel worker processes",
    )

    args = PARSER.parse_args()
    if args.mode == "preprocess":
        preprocessor = Preprocessor(args)
        preprocessor.preprocess_dataset()
        if os.path.exists("checksum.json"):
            verify_dataset(args.results_dir)

    if args.mode == "verify":
        verify_dataset(args.results_dir)
