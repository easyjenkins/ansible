#!/usr/bin/python
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = """
---
module: sros_command
version_added: "2.2"
author: "Peter Sprygada (@privateip)"
short_description: Run commands on remote devices running Nokia SR OS
description:
  - Sends arbitrary commands to an SR OS node and returns the results
    read from the device. This module includes an argument that will
    cause the module to wait for a specific condition before returning
    or timing out if the condition is not met.
  - This module does not support running commands in configuration mode.
    Please use M(sros_config) to configure SR OS devices.
extends_documentation_fragment: sros
options:
  commands:
    description:
      - List of commands to send to the remote SR OS device over the
        configured provider. The resulting output from the command
        is returned. If the I(wait_for) argument is provided, the
        module is not returned until the condition is satisfied or
        the number of retries has expired.
    required: true
  wait_for:
    description:
      - List of conditions to evaluate against the output of the
        command. The task will wait for each condition to be true
        before moving forward. If the conditional is not true
        within the configured number of retries, the task fails.
        See examples.
    required: false
    default: null
    aliases: ['waitfor']
  match:
    description:
      - The I(match) argument is used in conjunction with the
        I(wait_for) argument to specify the match policy.  Valid
        values are C(all) or C(any).  If the value is set to C(all)
        then all conditionals in the wait_for must be satisfied.  If
        the value is set to C(any) then only one of the values must be
        satisfied.
    required: false
    default: all
    choices: ['any', 'all']
  retries:
    description:
      - Specifies the number of retries a command should by tried
        before it is considered failed. The command is run on the
        target device every retry and evaluated against the
        I(wait_for) conditions.
    required: false
    default: 10
  interval:
    description:
      - Configures the interval in seconds to wait between retries
        of the command. If the command does not pass the specified
        conditions, the interval indicates how long to wait before
        trying the command again.
    required: false
    default: 1
"""

EXAMPLES = """
# Note: examples below use the following provider dict to handle
#       transport and authentication to the node.
---
vars:
  cli:
    host: "{{ inventory_hostname }}"
    username: admin
    password: admin
    transport: cli

---
tasks:
  - name: run show version on remote devices
    sros_command:
      commands: show version
      provider: "{{ cli }}"

  - name: run show version and check to see if output contains sros
    sros_command:
      commands: show version
      wait_for: result[0] contains sros
      provider: "{{ cli }}"

  - name: run multiple commands on remote nodes
    sros_command:
      commands:
        - show version
        - show port detail
      provider: "{{ cli }}"

  - name: run multiple commands and evaluate the output
    sros_command:
      commands:
        - show version
        - show port detail
      wait_for:
        - result[0] contains TiMOS-B-14.0.R4
      provider: "{{ cli }}"
"""

RETURN = """
stdout:
  description: The set of responses from the commands
  returned: always
  type: list
  sample: ['...', '...']

stdout_lines:
  description: The value of stdout split into a list
  returned: always
  type: list
  sample: [['...', '...'], ['...'], ['...']]

failed_conditions:
  description: The list of conditionals that have failed
  returned: failed
  type: list
  sample: ['...', '...']
"""
import time

from ansible.module_utils.sros import run_commands
from ansible.module_utils.sros import sros_argument_spec, check_args
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.network_common import ComplexList
from ansible.module_utils.netcli import Conditional
from ansible.module_utils.six import string_types

def to_lines(stdout):
    for item in stdout:
        if isinstance(item, string_types):
            item = str(item).split('\n')
        yield item

def parse_commands(module, warnings):
    command = ComplexList(dict(
        command=dict(key=True),
        prompt=dict(),
        answer=dict()
    ), module)
    commands = command(module.params['commands'])
    for index, item in enumerate(commands):
        if module.check_mode and not item['command'].startswith('show'):
            warnings.append(
                'only show commands are supported when using check mode, not '
                'executing `%s`' % item['command']
            )
        elif item['command'].startswith('conf'):
            module.fail_json(
                msg='sros_command does not support running config mode '
                    'commands.  Please use sros_config instead'
            )
    return commands

def main():
    """main entry point for module execution
    """
    argument_spec = dict(
        commands=dict(type='list', required=True),

        wait_for=dict(type='list', aliases=['waitfor']),
        match=dict(default='all', choices=['all', 'any']),

        retries=dict(default=10, type='int'),
        interval=dict(default=1, type='int')
    )

    argument_spec.update(sros_argument_spec)

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=True)

    result = {'changed': False}

    warnings = list()
    check_args(module, warnings)
    commands = parse_commands(module, warnings)
    result['warnings'] = warnings

    wait_for = module.params['wait_for'] or list()
    conditionals = [Conditional(c) for c in wait_for]

    retries = module.params['retries']
    interval = module.params['interval']
    match = module.params['match']

    while retries > 0:
        responses = run_commands(module, commands)

        for item in list(conditionals):
            if item(responses):
                if match == 'any':
                    conditionals = list()
                    break
                conditionals.remove(item)

        if not conditionals:
            break

        time.sleep(interval)
        retries -= 1

    if conditionals:
        failed_conditions = [item.raw for item in conditionals]
        msg = 'One or more conditional statements have not be satisfied'
        module.fail_json(msg=msg, failed_conditions=failed_conditions)


    result = {
        'changed': False,
        'stdout': responses,
        'stdout_lines': list(to_lines(responses))
    }

    module.exit_json(**result)


if __name__ == '__main__':
    main()
