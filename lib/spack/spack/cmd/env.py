# Copyright 2013-2019 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import sys
import re
import collections

import llnl.util.tty as tty
import llnl.util.filesystem as fs
from llnl.util.tty.colify import colify
from llnl.util.tty.color import colorize

import spack.config
import spack.schema.env
import spack.cmd.install
import spack.cmd.uninstall
import spack.cmd.modules
import spack.cmd.common.arguments as arguments
import spack.environment as ev
import spack.util.string as string
import spack.paths

description = "manage virtual environments"
section = "environments"
level = "short"


#: List of subcommands of `spack env`
subcommands = [
    'activate',
    'deactivate',
    'create',
    ['remove', 'rm'],
    ['list', 'ls'],
    ['status', 'st'],
    'loads',
    'harness',
]


#
# env activate
#
def env_activate_setup_parser(subparser):
    """set the current environment"""
    shells = subparser.add_mutually_exclusive_group()
    shells.add_argument(
        '--sh', action='store_const', dest='shell', const='sh',
        help="print sh commands to activate the environment")
    shells.add_argument(
        '--csh', action='store_const', dest='shell', const='csh',
        help="print csh commands to activate the environment")
    shells.add_argument(
        '-d', '--dir', action='store_true', default=False,
        help="force spack to treat env as a directory, not a name")

    subparser.add_argument(
        '-p', '--prompt', action='store_true', default=False,
        help="decorate the command line prompt when activating")
    subparser.add_argument(
        metavar='env', dest='activate_env',
        help='name of environment to activate')


def env_activate(args):
    env = args.activate_env
    if not args.shell:
        msg = [
            "This command works best with Spack's shell support",
            ""
        ] + spack.cmd.common.shell_init_instructions + [
            'Or, if you want to use `spack env activate` without initializing',
            'shell support, you can run one of these:',
            '',
            '    eval `spack env activate --sh %s`   # for bash/sh' % env,
            '    eval `spack env activate --csh %s`  # for csh/tcsh' % env,
        ]
        tty.msg(*msg)
        return 1

    if ev.exists(env) and not args.dir:
        spack_env = ev.root(env)
        short_name = env
        env_prompt = '[%s]' % env

    elif ev.is_env_dir(env):
        spack_env = os.path.abspath(env)
        short_name = os.path.basename(os.path.abspath(env))
        env_prompt = '[%s]' % short_name

    else:
        tty.die("No such environment: '%s'" % env)

    if spack_env == os.environ.get('SPACK_ENV'):
        tty.die("Environment %s is already active" % args.activate_env)

    if args.shell == 'csh':
        # TODO: figure out how to make color work for csh
        sys.stdout.write('setenv SPACK_ENV %s;\n' % spack_env)
        sys.stdout.write('alias despacktivate "spack env deactivate";\n')
        if args.prompt:
            sys.stdout.write('if (! $?SPACK_OLD_PROMPT ) '
                             'setenv SPACK_OLD_PROMPT "${prompt}";\n')
            sys.stdout.write('set prompt="%s ${prompt}";\n' % env_prompt)

    else:
        if 'color' in os.environ['TERM']:
            env_prompt = colorize('@G{%s} ' % env_prompt, color=True)

        sys.stdout.write('export SPACK_ENV=%s;\n' % spack_env)
        sys.stdout.write("alias despacktivate='spack env deactivate';\n")
        if args.prompt:
            sys.stdout.write('if [ -z "${SPACK_OLD_PS1}" ]; then\n')
            sys.stdout.write('export SPACK_OLD_PS1="${PS1}"; fi;\n')
            sys.stdout.write('export PS1="%s ${PS1}";\n' % env_prompt)


#
# env deactivate
#
def env_deactivate_setup_parser(subparser):
    """deactivate any active environment in the shell"""
    shells = subparser.add_mutually_exclusive_group()
    shells.add_argument(
        '--sh', action='store_const', dest='shell', const='sh',
        help="print sh commands to deactivate the environment")
    shells.add_argument(
        '--csh', action='store_const', dest='shell', const='csh',
        help="print csh commands to deactivate the environment")


def env_deactivate(args):
    if not args.shell:
        msg = [
            "This command works best with Spack's shell support",
            ""
        ] + spack.cmd.common.shell_init_instructions + [
            'Or, if you want to use `spack env activate` without initializing',
            'shell support, you can run one of these:',
            '',
            '    eval `spack env deactivate --sh`   # for bash/sh',
            '    eval `spack env deactivate --csh`  # for csh/tcsh',
        ]
        tty.msg(*msg)
        return 1

    if 'SPACK_ENV' not in os.environ:
        tty.die('No environment is currently active.')

    if args.shell == 'csh':
        sys.stdout.write('unsetenv SPACK_ENV;\n')
        sys.stdout.write('if ( $?SPACK_OLD_PROMPT ) '
                         'set prompt="$SPACK_OLD_PROMPT" && '
                         'unsetenv SPACK_OLD_PROMPT;\n')
        sys.stdout.write('unalias despacktivate;\n')

    else:
        sys.stdout.write('unset SPACK_ENV; export SPACK_ENV;\n')
        sys.stdout.write('unalias despacktivate;\n')
        sys.stdout.write('if [ -n "$SPACK_OLD_PS1" ]; then\n')
        sys.stdout.write('export PS1="$SPACK_OLD_PS1";\n')
        sys.stdout.write('unset SPACK_OLD_PS1; export SPACK_OLD_PS1;\n')
        sys.stdout.write('fi;\n')


#
# env create
#
def env_create_setup_parser(subparser):
    """create a new environment"""
    subparser.add_argument(
        'create_env', metavar='ENV', help='name of environment to create')
    subparser.add_argument(
        '-d', '--dir', action='store_true',
        help='create an environment in a specific directory')
    subparser.add_argument(
        'envfile', nargs='?', default=None,
        help='optional init file; can be spack.yaml or spack.lock')


def env_create(args):
    if args.envfile:
        with open(args.envfile) as f:
            _env_create(args.create_env, f, args.dir)
    else:
        _env_create(args.create_env, None, args.dir)


def _env_create(name_or_path, init_file=None, dir=False):
    """Create a new environment, with an optional yaml description.

    Arguments:
        name_or_path (str): name of the environment to create, or path to it
        init_file (str or file): optional initialization file -- can be
            spack.yaml or spack.lock
        dir (bool): if True, create an environment in a directory instead
            of a named environment
    """
    if dir:
        env = ev.Environment(name_or_path, init_file)
        env.write()
        tty.msg("Created environment in %s" % env.path)
    else:
        env = ev.create(name_or_path, init_file)
        env.write()
        tty.msg("Created environment '%s' in %s" % (name_or_path, env.path))
    return env


#
# env remove
#
def env_remove_setup_parser(subparser):
    """remove an existing environment"""
    subparser.add_argument(
        'rm_env', metavar='ENV', nargs='+',
        help='environment(s) to remove')
    arguments.add_common_arguments(subparser, ['yes_to_all'])


def env_remove(args):
    """Remove a *named* environment.

    This removes an environment managed by Spack. Directory environments
    and `spack.yaml` files embedded in repositories should be removed
    manually.
    """
    read_envs = []
    for env_name in args.rm_env:
        env = ev.read(env_name)
        read_envs.append(env)

    if not args.yes_to_all:
        answer = tty.get_yes_or_no(
            'Really remove %s %s?' % (
                string.plural(len(args.rm_env), 'environment', show_n=False),
                string.comma_and(args.rm_env)),
            default=False)
        if not answer:
            tty.die("Will not remove any environments")

    for env in read_envs:
        if env.active:
            tty.die("Environment %s can't be removed while activated.")

        env.destroy()
        tty.msg("Successfully removed environment '%s'" % env.name)


#
# env list
#
def env_list_setup_parser(subparser):
    """list available environments"""


def env_list(args):
    names = ev.all_environment_names()

    color_names = []
    for name in names:
        if ev.active(name):
            name = colorize('@*g{%s}' % name)
        color_names.append(name)

    # say how many there are if writing to a tty
    if sys.stdout.isatty():
        if not names:
            tty.msg('No environments')
        else:
            tty.msg('%d environments' % len(names))

    colify(color_names, indent=4)


#
# env status
#
def env_status_setup_parser(subparser):
    """print whether there is an active environment"""


def env_status(args):
    env = ev.get_env(args, 'env status')
    if env:
        if env.path == os.getcwd():
            tty.msg('Using %s in current directory: %s'
                    % (ev.manifest_name, env.path))
        else:
            tty.msg('In environment %s' % env.name)
    else:
        tty.msg('No active environment')


#
# env loads
#
def env_loads_setup_parser(subparser):
    """list modules for an installed environment '(see spack module loads)'"""
    subparser.add_argument(
        'env', nargs='?', help='name of env to generate loads file for')
    subparser.add_argument(
        '-m', '--module-type', choices=('tcl', 'lmod'),
        help='type of module system to generate loads for')
    spack.cmd.modules.add_loads_arguments(subparser)


def env_loads(args):
    env = ev.get_env(args, 'env loads', required=True)

    # Set the module types that have been selected
    module_type = args.module_type
    if module_type is None:
        # If no selection has been made select all of them
        module_type = 'tcl'

    recurse_dependencies = args.recurse_dependencies
    args.recurse_dependencies = False

    loads_file = fs.join_path(env.path, 'loads')
    with open(loads_file, 'w') as f:
        specs = env._get_environment_specs(
            recurse_dependencies=recurse_dependencies)

        spack.cmd.modules.loads(module_type, specs, args, f)

    print('To load this environment, type:')
    print('   source %s' % loads_file)


#
# env harness
#
def env_harness_setup_parser(subparser):
    """create a harness for user compilation of "setup" programs to be
    built and installed outside of Spack installation location."""
    subparser.add_argument(
        'env', nargs='?', help='name of env to generate loads file for')
    subparser.add_argument(
        '-o', '--output', default=None,
        help='directory in which to store harness source and CMake setup scripts.')

install_prefixRE = re.compile(r'^\s*-DCMAKE_INSTALL_PREFIX\:PATH=(.*)$', re.MULTILINE)


# https://gist.github.com/carlsmith/b2e6ba538ca6f58689b4c18f46fef11c
def replace(string, substitutions):
    def _sub(match):
        print('matched {0}'.format(match.group(0)))
        ret = substitutions[match.group(0)]
        return ret

    substrings = sorted(substitutions, key=len, reverse=True)
    regex = re.compile('|'.join(map(re.escape, substrings)))
    return regex.sub(_sub, string)

SetupFile = collections.namedtuple('SetupFile', ('pkg', 'ifsetup', 'ofsetup', 'setup'))

def env_harness(args):
    env = ev.get_env(args, 'env harness', required=True)
    harness_home = os.path.abspath(env.name) if args.output is None else os.path.abspath(args.output)
    opt = os.path.join(harness_home, 'opt')


    # Read setup files
    setups = []
    for pkg in [x[:-9] for x in os.listdir(env.path) if x.endswith('-setup.py')]:
        ifsetup = os.path.join(env.path, pkg+'-setup.py')
        ofsetup = os.path.join(harness_home, pkg+'-setup.py')
        with open(ifsetup) as fin:
            setup = fin.read()
        setups.append(SetupFile(pkg, ifsetup, ofsetup, setup))

    # Replacements to make in the setup files
    repl = {
        r'export SPACK_ENV_DIR=' : 'export SPACK_ENV_DIR={0} #'.format(env.path),
        r'export HARNESS_HOME=' : 'export HARNESS_HOME={0} #'.format(harness_home),
    }
    for ss in setups:
        match = install_prefixRE.search(ss.setup)
        loc0 = match.group(1)    # Old install location of this package
        # loc1 = os.path.join(opt, ss.pkg)  # Don't need hashes in new location
        repl[loc0] = opt

    # Add in the loads file
    for fname in ('loads', 'loads-x'):
        ifsetup = os.path.join(env.path, fname)
        ofsetup = os.path.join(harness_home, fname)
        with open(ifsetup) as fin:
            setup = fin.read()
        setups.append(SetupFile('__'+fname, ifsetup, ofsetup, setup))


    # Write new files
    if not os.path.isdir(harness_home):
        os.makedirs(harness_home)
    for ss in setups:
        print('Writing {0}'.format(ss.ofsetup))
        with open(ss.ofsetup, 'w') as out:
            out.write(replace(ss.setup, repl))



#: Dictionary mapping subcommand names and aliases to functions
subcommand_functions = {}

#
# spack env
#
def setup_parser(subparser):
    sp = subparser.add_subparsers(metavar='SUBCOMMAND', dest='env_command')

    for name in subcommands:
        if isinstance(name, (list, tuple)):
            name, aliases = name[0], name[1:]
        else:
            aliases = []

        # add commands to subcommands dict
        function_name = 'env_%s' % name
        function = globals()[function_name]
        for alias in [name] + aliases:
            subcommand_functions[alias] = function

        # make a subparser and run the command's setup function on it
        setup_parser_cmd_name = 'env_%s_setup_parser' % name
        setup_parser_cmd = globals()[setup_parser_cmd_name]

        subsubparser = sp.add_parser(
            name, aliases=aliases, help=setup_parser_cmd.__doc__)
        setup_parser_cmd(subsubparser)


def env(parser, args):
    """Look for a function called environment_<name> and call it."""
    action = subcommand_functions[args.env_command]
    action(args)
