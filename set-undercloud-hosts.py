#!/usr/bin/env python
from novaclient import client
from subprocess import call
from os import environ, system, getuid
import sys
import re

"""
Script to set hostnames / IP addresses mapping
in /etc/hosts
"""

try:
    USERNAME = environ['OS_USERNAME']
    PASSWORD = environ['OS_PASSWORD']
    AUTH_URL = environ['OS_AUTH_URL']
except Exception as e:
    raise Exception("Missing one or more authentication details: %s" % e)

try:
    PROJECT_NAME = environ['OS_PROJECT_NAME']
except Exception as e:
    PROJECT_NAME = environ['OS_TENANT_NAME']

try:
    OS_CLOUD = environ['OS_CLOUDNAME']
except Exception as e:
    raise Exception("Missing OS_CLOUDNAME")

if OS_CLOUD != 'undercloud':
    raise Exception("You need to load the undercloud authentication details")


def replace_in_file(output):
    if getuid() != 0:
        print "You need to be root to edit /etc/hosts."
        print "Try to use 'sudo -E ...'"
        sys.exit(1)

    # Remove older entries if any
    try:
        # Yep, perl, funny ah?
        call(["perl -i -p0e 's/###setHostsStart###.*?###setHostsEnd###\n//s' /etc/hosts"],
             shell=True)
    except OSError as e:
        print "OSError > ",e.errno
        print "OSError > ",e.strerror
        print "OSError > ",e.filename
    except:
        print "Error > ",sys.exc_info()[0]

    # Append new
    try:
        file = open('/etc/hosts', 'a')
    except IOError as e:
        raise IOError("Error opening file for write: %s", e)
    else:
        file.write(output)
        file.close()


def main():

    """ Example names:
        overcloud-controller-2
        overcloud-novacompute-0 """

    # Regex to extract short name from
    full_name_regex = r'^overcloud\-(.+?)$'

    nova = client.Client('2', USERNAME, PASSWORD, PROJECT_NAME,
                         AUTH_URL, connection_pool=True)

    prep_list = dict()

    # Get all servers
    servers = nova.servers.list()

    for server in servers:

        # Get networks/IP for ctlplane
        networks = server.networks
        if ('ctlplane' in networks and len(networks['ctlplane'])):

            short_name = ''

            # Extract shortnames
            m = re.search(full_name_regex, server.name)
            if m:
                short_name_prep = m.group(1)
                short_name_prep = re.sub('-','', short_name_prep)
                short_name = re.sub('nova','', short_name_prep)

            # Save in temporary dict
            prep_list[networks['ctlplane'][0]] = server.name + ' ' + short_name

    output = '###setHostsStart###\n'
    for k, v in prep_list.items():
        output +=  "%s\t%s\n" % (k ,v)
    output += '###setHostsEnd###\n'

    if '-a' in sys.argv:
        replace_in_file(output)
    else:
        print "Add the following to your /etc/hosts:\n"
        print output


if __name__ == "__main__":

    if '-h' in sys.argv:
        print """Script will output the overcloud hosts and their respective IP addresses.
Use -a to automatically update /etc/hosts"""
        sys.exit(0)

    main()
