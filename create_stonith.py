#!/usr/bin/env python
import os
import json
import sys
from pprint import pprint
from keystoneauth1 import identity
from keystoneauth1 import session
from ironicclient import client as ironic_client
from novaclient import client as nova_client

"""
Credit to: https://github.com/rscarazz/tripleo-director-instance-ha/blob/master/create-stonith-from-instackenv.py
Outputs commands to run on pcs cluster to get stonith enabled
Based on the IPMI addresses (or SSH address) of the controllers
"""

# Environmenova variables (need to source before launching):
# export NOVA_VERSION=1.1
# export OS_PASSWORD=$(sudo hiera admin_password)
# export OS_AUTH_URL=http://192.0.2.1:5000/v2.0
# export OS_USERNAME=admin
# export OS_TENANT_NAME=admin # <- or OS_PROJECT_NAME
# export COMPUTE_API_VERSION=1.1
# export OS_NO_CACHE=True

# JSON format:
#{ "nodes": [
#{
#  "mac": [
#"b8:ca:3a:66:e3:82"
#  ],
#  "_comment":"host12-rack03.scale.openstack.engineering.redhat.com",
#  "cpu": "",
#  "memory": "",
#  "disk": "",
#  "arch": "x86_64",
#  "pm_type":"pxe_ipmitool",
#  "pm_user":"qe-scale",
#  "pm_password":"d0ckingSt4tion",
#  "pm_addr":"10.1.8.102"
#},
#...


def run():
    # Verify we've loaded overcloud environment
    try:
        os.environ['OS_CLOUDNAME']
    except:
        pass
    else:
        if os.environ['OS_CLOUDNAME'] != 'undercloud':
            sys.stderr.write("Undercloud auth details required."
                             " Make sure you source ~/stackrc!\n")
            sys.exit(1)

    # Get location of instackenv.json
    try:
        jdata = open(sys.argv[1])
    except IndexError as e:
        sys.stderr.write("Missing the instackenv.json file location as"
                         " first argument\n")
        sys.exit(1)

    # Load instackenv.json data
    data = json.load(jdata)
    jdata.close()

    # Load openstack auth details
    os_username = os.environ['OS_USERNAME']
    os_password = os.environ['OS_PASSWORD']
    os_auth_url = os.environ['OS_AUTH_URL']
    try:
        os_tenant_name = os.environ['OS_TENANT_NAME']
    except:
        os_tenant_name = os.environ['OS_PROJECT_NAME']

    # Create the create-virt-key.sh script
    create_key_script()

    # Auth to nova
    auth = identity.Password(auth_url=os_auth_url,
                             username=os_username,
                             password=os_password,
                             project_name=os_tenant_name)

    sess = session.Session(auth=auth)
    try:
        nova = nova_client.Client(2,
                                  session=sess)
    except Exception as e:
        raise Exception("Error: %s" % e)

    # Auth to ironic
    kwargs = {'os_username': os_username,
              'os_password': os_password,
              'os_auth_url': os_auth_url,
              'os_project_name': os_tenant_name}

    try:
        ironic = ironic_client.get_client(1, **kwargs)
    except Exception as e:
        raise Exception("Error: %s" % e)



    # Start printing out config commands
    print('pcs property set stonith-enabled=false')

    hosts={}
    for instance in nova.servers.list():
        print('pcs stonith delete stonith-{} || /bin/true'.format(instance.name))
        ironic_node = ironic.node.get_by_instance_uuid(instance.id)
        # With IPMI address
        if not ironic_node.driver_info.has_key("ipmi_address"):
            if instance.name.find("control") > 0:
                print('cat %s | ssh %s -- "cat > fence_prep.sh; sudo bash fence_prep.sh"' %
                      ("create-virt-key.sh", instance.addresses["ctlplane"][0]["addr"]))
                ip = ironic_node.driver_info["ssh_address"]
                hosts[ip] = ip
        # Without IPMI address
        else:
            for node in data["nodes"]:
                if (node["pm_addr"] == ironic_node.driver_info["ipmi_address"] and \
                    'controller' in instance.name):
                    print('pcs stonith create stonith-{} fence_ipmilan'
                          ' pcmk_host_list="{}" ipaddr="{}" action="poweroff"'
                          ' login="{}" passwd="{}" lanplus="true" delay=20'
                          ' op monitor interval=60s'.format(instance.name,
                                                            instance.name,
                                                            node["pm_addr"],
                                                            node["pm_user"],
                                                            node["pm_password"]))
    # Only when no IPMI address
    for host in hosts:
        print "INSIDE"
        virt_file = "fence-{}-prep.sh".format(hosts[host])
        fence_virt_prep="""
wget http://download.eng.bos.redhat.com/brewroot/work/tasks/2585/10972585/fence-virt-{,debuginfo-}0.3.2-3.el7_2.x86_64.rpm
wget http://download.eng.bos.redhat.com/brewroot/work/tasks/2585/10972585/fence-virtd-{,libvirt-,multicast-,tcp-}0.3.2-3.el7_2.x86_64.rpm
yum install -y fence-*.rpm
mkdir -p /etc/cluster/
echo -n \$(head -c 16 /dev/urandom | od -An -t x | tr -d ' ') > /etc/cluster/fence_xvm.key
chmod a+r /etc/cluster/fence_xvm.key
chmod a+rx /etc/cluster/
sed -i -e s/system/session/ -e s/multicast/tcp/ -e s/225.0.0.12/%s/ /etc/fence_virt.conf 
echo "User=stack" >> /usr/lib/systemd/system/fence_virtd.service
sed -i 's@FENCE_VIRTD_ARGS$@FENCE_VIRTD_ARGS -p /tmp/fence_virtd_stack.pid@' /usr/lib/systemd/system/fence_virtd.service
systemctl enable fence_virtd.service
service fence_virtd start
""" % host
        os.system("cat << END > %s\n%s\nEND" %(virt_file, fence_virt_prep))

        print('cat %s | ssh -l root %s -- "cat > fence_prep.sh; bash fence_prep.sh"' %
              (virt_file, host))
        print('pcs stonith create fence-overcloud-{} fence_virt ipaddr={}'.format(host, host))

    print('pcs property set stonith-enabled=true')


def create_key_script():
    try:
        os.system("cat << END > create-virt-key.sh\nmkdir -p /etc/cluster/&&chmod 700 /etc/cluster/\n"
                  "echo -n \$(head -c 16 /dev/urandom | od -An -t x | tr -d ' ') > "
                  "/etc/cluster/fence_xvm.key\nchmod 400 /etc/cluster/fence_xvm.key\nEND")
    except Exception as e:
        sys.stderr.write("Failed to create create-virt-key.sh: %e" % e)
        sys.exit(1)


if __name__ == "__main__":
    run()
