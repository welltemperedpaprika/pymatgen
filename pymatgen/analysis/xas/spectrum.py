# coding: utf-8
# Copyright (c) Pymatgen Development Team.
# Distributed under the terms of the MIT License.

"""
This module defines classes to represent all xas and stitching methods
"""
import math
from scipy.interpolate import interp1d
import numpy as np
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.core.spectrum import Spectrum
from typing import List

__author__ = "Chen Zheng, Yiming Chen"
__copyright__ = "Copyright 2012, The Materials Project"
__version__ = "3.0"
__maintainer__ = "Yiming Chen"
__email__ = "chz022@ucsd.edu, yic111@ucsd.edu"
__date__ = "Jan 26, 2020"


class XAS(Spectrum):
    """
    Basic XAS object.

    Args:
        x: A sequence of x-ray energies in eV
        y: A sequence of mu(E)
        structure (Structure): Structure associated with the spectrum
        absorbing_element (Element): Element associated with the spectrum
        edge (str): Absorption edge associated with the spectrum
        spectrum_type (str): 'XANES' or 'EXAFS'


    .. attribute: x
        The sequence of energies

    .. attribute: y
        The sequence of mu(E)

    .. attribute: absorbing_element
        The absorbing_element of the spectrum

    .. attribute: edge
        The edge of the spectrum

    .. attribute: spectrum_type
        XANES or EXAFS spectrum

    """
    XLABEL = 'Energy'
    YLABEL = 'Intensity'

    def __init__(self, x, y, structure, absorbing_element, edge="K",
                 spectrum_type="XANES"):
        """
        Initializes a spectrum object.
        """

        super(XAS, self).__init__(x, y, structure, absorbing_element,
                                  edge)
        self.structure = structure
        self.absorbing_element = absorbing_element
        self.edge = edge
        self.spectrum_type = spectrum_type
        self.e0 = self.x[np.argmax(np.gradient(self.y) /
                                   np.gradient(self.x))]
        # Wavenumber, k is calculated based on equation
        #             k^2=2*m/(hbar)^2*(E-E0)
        self.k = [np.sqrt((i-self.e0) / 3.8537) if i > self.e0 else
                  -np.sqrt((self.e0-i) / 3.8537) for i in self.x]

    def __str__(self):
        return "%s %s Edge %s for %s: %s" % (
            self.absorbing_element, self.edge, self.spectrum_type,
            self.structure.composition.reduced_formula,
            super(XAS, self).__str__()
        )

    def stitch(self, other: 'XAS', num_samples: int = 500, mode: str = "XAFS") \
            -> 'XAS':

        """
        Stitch XAS objects to get the full XAFS spectrum or L23 edge XANES
        spectrum depending on the mode.

        1. Use XAFS mode for stitching XANES and EXAFS with same absorption edge.
            The stitching will be performed based on wavenumber, k.
            for k <= 3, XAS(k) = XAS[XANES(k)]
            for 3 < k < max(xanes_k), will interpolate according to
                XAS(k)=f(k)*mu[XANES(k)]+(1-f(k))*mu[EXAFS(k)]
                where f(k)=cos^2((pi/2) (k-3)/(max(xanes_k)-3)
            for k > max(xanes_k), XAS(k) = XAS[EXAFS(k)]
        2. Use L23 mode for stitching L2 and L3 edge XANES for elements with
            atomic number <=30.

        Args:
            other: Another XAS object.
            num_samples(int): Number of samples for interpolation.
            mode(str): Either XAFS mode for stitching XANES and EXAFS
                        or L23 mode for stitching L2 and L3.

        Returns:
            XAS object: The stitched spectrum.
        """
        m = StructureMatcher()
        if not m.fit(self.structure, other.structure):
            raise ValueError(
                "The input structures from spectra mismatch")
        if not self.absorbing_element == other.absorbing_element:
            raise ValueError("The absorbing element from spectra are different")

        if mode == "XAFS":
            if not self.edge == other.edge:
                raise ValueError("Only spectrum with the same absorption "
                                 "edge can be stitched in XAFS mode.")
            if self.spectrum_type == other.spectrum_type:
                raise ValueError("Need one XANES and one EXAFS spectrum to "
                                 "stitch in XAFS mode")

            xanes = self if self.spectrum_type == "XANES" else other
            exafs = self if self.spectrum_type == "EXAFS" else other
            if max(xanes.x) < min(exafs.x):
                raise ValueError(
                    "Energy overlap between XANES and EXAFS is needed for stitching")

            # for k <= 3
            wavenumber, mu = [], []  # type: List[float],  List[float]
            idx = xanes.k.index(min(self.k, key=lambda x: (abs(x - 3), x)))
            mu.extend(xanes.y[:idx])
            wavenumber.extend(xanes.k[:idx])

            # for 3 < k < max(xanes.k)
            fs = []  # type: List[float]
            ks = np.linspace(3, max(xanes.k), 50)
            for k in ks:
                f = np.cos((math.pi / 2) * (k - 3) / (max(xanes.k) - 3)) ** 2
                fs.append(f)
            f_xanes = interp1d(
                np.asarray(xanes.k), np.asarray(xanes.y),
                bounds_error=False, fill_value=0)
            f_exafs = interp1d(
                np.asarray(exafs.k), np.asarray(exafs.y),
                bounds_error=False, fill_value=0)
            mu_xanes = f_xanes(ks)
            mu_exafs = f_exafs(ks)
            mus = [fs[i] * mu_xanes[i] + (1 - fs[i]) * mu_exafs[i] for i in
                   np.arange(len(ks))]
            mu.extend(mus)
            wavenumber.extend(ks)

            # for k > max(xanes.k)
            idx = exafs.k.index(min(exafs.k, key=lambda x: (abs(x - max(xanes.k)))))
            mu.extend(exafs.y[idx:])
            wavenumber.extend(exafs.k[idx:])

            # interpolation
            f_final = interp1d(
                np.asarray(wavenumber), np.asarray(mu), bounds_error=False,
                fill_value=0)
            wavenumber_final = np.linspace(min(wavenumber), max(wavenumber),
                                           num=num_samples)
            mu_final = f_final(wavenumber_final)
            energy_final = [3.8537 * i ** 2 + xanes.e0 if i > 0 else
                            -3.8537 * i ** 2 + xanes.e0 for i in wavenumber_final]
            return XAS(energy_final, mu_final, self.structure,
                       self.absorbing_element, xanes.edge, "XAFS")

        if mode == "L23":
            if not self.spectrum_type == "XANES" and \
                    other.spectrum_type == "XANES":
                raise ValueError("Only XANES spectrum can be stitched in "
                                 "L23 mode.")
            if self.edge not in ["L2", "L3"] or other.edge not in ["L2", "L3"] \
                    or self.edge == other.edge:
                raise ValueError("Need one L2 and one L3 edge spectrum to stitch"
                                 "in L23 mode.")
            l2_xanes = self if self.edge == "L2" else other
            l3_xanes = self if self.edge == "L3" else other
            if l2_xanes.absorbing_element.number > 30:
                raise ValueError(
                    "Does not support L2,3-edge XANES for {} element"
                    .format(l2_xanes.absorbing_element))

            l2_f = interp1d(
                l2_xanes.x, l2_xanes.y, bounds_error=False, fill_value=0)
            # will add value of l3.y[-1] to avoid sudden change in absorption coeff.
            l3_f = interp1d(
                l3_xanes.x, l3_xanes.y, bounds_error=False,
                fill_value=l3_xanes.y[-1])
            energy = np.linspace(min(l3_xanes.x), max(l2_xanes.x),
                                 num=num_samples)
            mu = [i + j for i, j in zip(l2_f(energy), l3_f(energy))]
            return XAS(energy, mu, self.structure, self.absorbing_element,
                       "L23", "XANES")

        else:
            raise ValueError("Invalid mode. Only XAFS and L23 are supported.")
