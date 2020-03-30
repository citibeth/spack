# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack import *


class Ladot(Package):
    """Ladot is a script that makes using LaTeX in graphs generated by dot
    (graphviz) relatively easy."""

    homepage = "https://brighten.bigw.org/projects/ladot/"
    url      = "https://brighten.bigw.org/projects/ladot/ladot-1.2.tar.gz"

    version('1.2', sha256='f829eeca829b82c0315cd87bffe410bccab96309b86b1c883b3ddaa93170f25e')

    depends_on('perl', type=('run', 'test'))
    depends_on('graphviz', type=('run', 'test'))
    depends_on('texlive', type='test')

    def install(self, spec, prefix):
        if self.run_tests:
            with working_dir('example'):
                make()

        mkdir(prefix.bin)
        install('ladot', prefix.bin)