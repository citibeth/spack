# Copyright 2013-2019 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack import *


class PyNetcdf4(PythonPackage):
    """Python interface to the netCDF Library."""

    homepage = "https://github.com/Unidata/netcdf4-python"
    url      = "https://pypi.io/packages/source/n/netCDF4/netCDF4-1.2.7.tar.gz"

    version('1.2.7',   '77b357d78f9658dd973dee901f6d86f8')
    version('1.2.3.1', '24fc0101c7c441709c230e76af611d53')

    depends_on('py-setuptools',   type='build')
    depends_on('py-cython@0.19:', type='build')

    depends_on('py-numpy@1.7:', type=('build', 'run'))

    depends_on('netcdf@4:')
    depends_on('hdf5@1.8.0:')
