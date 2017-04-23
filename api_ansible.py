#!/usr/bin/env python
import os
import sys
import json
from collections import namedtuple

from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.inventory import Inventory
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.plugins.callback import CallbackBase
from ansible.playbook.play import Play
from ansible.executor.task_queue_manager import TaskQueueManager


class ResultCallback(CallbackBase):

    def v2_runner_on_ok(self, result, **kwargs):
        host = result._host
        print json.dumps({host.name: result._result}, indent=4)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        host = result._host
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if 'exception' in result._result:
            error = result._result['exception'].strip().split('\n')[-1]
            print json.dumps({host.name: error}, indent=4)
            del result._result['exception']

        if result._task.loop and 'results' in result._result:
            pass
        else:
            error = "fatal: [%s]: FAILED! => %s" % (result._host.get_name(), result._result)
            print json.dumps({host.name: error}, indent=4)

    def v2_runner_on_unreachable(self, result):
        host = result._host
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if delegated_vars:
            error = "fatal: [%s -> %s]: UNREACHABLE! => %s" % (result._host.get_name(), delegated_vars['ansible_host'], result._result)
        else:
            error = "fatal: [%s]: UNREACHABLE! => %s" % (result._host.get_name(), result._result)
        print json.dumps({host.name: error}, indent=4)


###############################################
# Set server name/ip here.
# The name/password/port will be passed to
# this module if we integrate it into Cockpit
server = 'example.com'
port = 2222
password = 'change_me'
username = 'root'
###############################################

connection_timeout = 10
ssh_global_args = '-o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no -o ConnectTimeout=%s -o Port=%s' % (connection_timeout, port)
results_callback = ResultCallback()
variable_manager = VariableManager()
loader = DataLoader()
inventory = Inventory(loader=loader, variable_manager=variable_manager,  host_list=[server])

Options = namedtuple('Options', ['listtags',
                 'listtasks',
                 'listhosts',
                 'syntax',
                 'connection',
                 'module_path',
                 'forks',
                 'remote_user',
                 'private_key_file',
                 'ssh_common_args',
                 'ssh_extra_args',
                 'sftp_extra_args',
                 'scp_extra_args',
                 'become',
                 'become_method',
                 'become_user',
                 'verbosity',
                 'check'])

options = Options(listtags=False,
          listtasks=False,
          listhosts=False,
          syntax=False,
          connection='ssh',
          module_path=None,
          forks=10,
          remote_user=username,
          private_key_file=None,
          ssh_common_args=ssh_global_args,
          ssh_extra_args=ssh_global_args,
          sftp_extra_args=ssh_global_args,
          scp_extra_args=ssh_global_args,
          become=True,
          become_method='sudo',
          become_user='root',
          verbosity=True,
          check=False)

passwords = dict(conn_pass=password)

play_source =  dict(
        name = "Ansible Play",
        hosts = 'all',
        gather_facts = 'yes',
        tasks = [ 
            # Example shell command
            dict(action=dict(module='shell', args='updtime')),
            # Example running other stuff:
            dict(action=dict(module='shell', args="""date -d@$(awk '{print $1}' /proc/uptime) +'%j %T' | awk '{print $1-1"d",$2}'')),
         ]
    )
play = Play().load(play_source, variable_manager=variable_manager, loader=loader)

tqm = None
try:
    tqm = TaskQueueManager(
              inventory=inventory,
              variable_manager=variable_manager,
              loader=loader,
              options=options,
              passwords=passwords,
              stdout_callback=results_callback,
          )
    result = tqm.run(play)
except Exception as e:
    raise Exception("Error: %s" % e)
finally:
    if tqm is not None:
        tqm.cleanup()
