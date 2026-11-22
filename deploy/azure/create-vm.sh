#!/usr/bin/env bash
# deploy/azure/create-vm.sh — Phase 2 host (issue #141): one always-on Linux
# VM on an Azure for Students subscription. Run from the maintainer's machine
# after `az login`; it creates only Azure resources, nothing on this host.
#
#   bash deploy/azure/create-vm.sh
#
# Choices measured on 2026-11-22 against this subscription, not assumed:
# - Region: the student subscription only allows brazilsouth, italynorth,
#   spaincentral, northcentralus and canadacentral (Azure Policy "Allowed
#   resource deployment regions"). The free-tier sizes are NOT offered in
#   brazilsouth for it; northcentralus offers Standard_B2ats_v2 (AMD) and
#   Standard_B2pts_v2 (Arm). Distance does not matter for a 5-minute poller.
# - Size: Standard_B2ats_v2 (2 vCPU, 1 GiB) — x86, so every wheel installs as
#   on the dev machine. The collector peaks at 68 MB RAM.
# - OS disk: 64 GiB Premium SSD = P6, the managed-disk size the free tier
#   covers. A different size or tier draws from the USD 100 credit.
# - Public IP: Standard SKU, static. NOT covered by the free VM hours —
#   expected to be the main credit burn; measure it in the first week.
# - Access: SSH public key only (password authentication disabled), inbound
#   port 22 only. The private key never leaves the maintainer's machine.
set -euo pipefail

SUBSCRIPTION="${AZURE_SUBSCRIPTION:-Azure for Students}"
LOCATION=northcentralus
RESOURCE_GROUP=alertavida-rg
VM_NAME=alertavida-vm
VM_SIZE=Standard_B2ats_v2
IMAGE=Canonical:ubuntu-24_04-lts:server:latest
ADMIN_USER=maintainer
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-$HOME/.ssh/id_ed25519.pub}"

if [ ! -f "$SSH_PUBLIC_KEY" ]; then
    echo "SSH public key not found at $SSH_PUBLIC_KEY" >&2
    exit 1
fi

az account set --subscription "$SUBSCRIPTION"

echo "== 1/3: resource providers (one-time per subscription, free) =="
for ns in Microsoft.Compute Microsoft.Network; do
    az provider register --namespace "$ns" --wait
    echo "$ns: $(az provider show -n "$ns" --query registrationState -o tsv)"
done

echo "== 2/3: resource group =="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

echo "== 3/3: VM =="
az vm create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --location "$LOCATION" \
    --size "$VM_SIZE" \
    --image "$IMAGE" \
    --admin-username "$ADMIN_USER" \
    --authentication-type ssh \
    --ssh-key-values "$SSH_PUBLIC_KEY" \
    --os-disk-size-gb 64 \
    --storage-sku Premium_LRS \
    --public-ip-sku Standard \
    --nsg-rule SSH \
    --output table

IP="$(az vm show -d -g "$RESOURCE_GROUP" -n "$VM_NAME" --query publicIps -o tsv)"
echo
echo "=== VM READY — ssh $ADMIN_USER@$IP ==="
