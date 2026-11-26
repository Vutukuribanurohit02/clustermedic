#!/usr/bin/env bash
# Copy the bundled DMTF mockup out of the container so the fault injector can edit it.
set -euo pipefail
dest=infra/redfish/mockups/public-rackmount1
if [ -d "$dest" ]; then echo "mockup already at $dest"; exit 0; fi
src=$(docker exec redfish sh -c 'find / -type d -name public-rackmount1 2>/dev/null | head -1')
if [ -z "$src" ]; then echo "public-rackmount1 not found inside the redfish container" >&2; exit 1; fi
mkdir -p infra/redfish/mockups
docker cp "redfish:$src" "$dest"
echo "copied $src -> $dest"
find "$dest" -path '*Chassis/1U/Thermal/index.json'
