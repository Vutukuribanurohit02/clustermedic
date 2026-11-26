---
id: RB-009
title: Network MTU mismatch between nodes
fault_type: mtu_mismatch
components: [network, slurm]
severity: medium
destructive_actions: [change_network_config]
---

## Symptoms
- Small messages work, large transfers hang: `ssh` connects but `scp` stalls, NFS mounts hang on large reads.
- MPI or multi-node jobs hang or time out, while single-node jobs work.
- Only jobs that include one specific node are affected.

## Diagnose (read-only)
1. Compare interface MTU on each node: `ip link show` (look at `mtu`). All nodes on the same network must match.
2. Test the full-size path without fragmentation. For a 9000-byte (jumbo) network: `ping -M do -s 8972 -c 3 <peer>`. For 1500: `ping -M do -s 1472 -c 3 <peer>`. The size is the MTU minus 28 bytes of IP and ICMP headers.
3. If the large ping fails (`message too long` or no reply) but a small `ping <peer>` works, there is an MTU mismatch on the path.
4. `tracepath <peer>` reports the path MTU it discovers.
5. Check whether the node was recently rebooted or reconfigured; a non-persistent MTU change is lost on reboot.

## Common causes
- One node's interface reverted to the default 1500 after a reboot, while the cluster uses jumbo frames (9000).
- A configuration change applied to some nodes but not others.
- A switch port configured with a different MTU than the nodes.

## Fix
- Set the node's MTU to the cluster standard: `ip link set dev <iface> mtu <value>` (**needs human approval**). This is temporary until the persistent network configuration is fixed.
- Fix the persistent configuration (netplan, NetworkManager or config management) so it survives a reboot (**needs human approval**).
- Drain the node while fixing if jobs are failing (**needs human approval**).

## Verify
- The full-size `ping -M do` test succeeds in both directions between the node and its peers.
- A multi-node test job completes.

## Escalate if
- All node MTUs match but large pings still fail (switch-side problem, needs the network team).
