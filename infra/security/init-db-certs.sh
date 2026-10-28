#!/bin/sh
set -eu

if [ -f /postgres/server.key ] && [ -f /mongo/server.pem ]; then
  exit 0
fi

mkdir -p /ca /postgres /mongo /tmp/nuam-db-certs
cd /tmp/nuam-db-certs

openssl genrsa -out ca.key 3072
openssl req -x509 -new -key ca.key -sha256 -days 3650 \
  -subj "/CN=NUAM local database CA" -out ca.crt

for service in postgres mongo; do
  openssl genrsa -out "${service}.key" 2048
  openssl req -new -key "${service}.key" \
    -subj "/CN=${service}" -out "${service}.csr"
  printf 'subjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n' \
    "$service" > "${service}.ext"
  openssl x509 -req -in "${service}.csr" -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out "${service}.crt" -days 825 -sha256 \
    -extfile "${service}.ext"
done

cp ca.crt /ca/postgres-ca.pem
cp ca.crt /ca/mongo-ca.pem
cp postgres.crt /postgres/server.crt
cp postgres.key /postgres/server.key
cat mongo.crt mongo.key > /mongo/server.pem
cp ca.crt /mongo/ca.pem

chown 70:70 /postgres/server.crt /postgres/server.key
chmod 644 /postgres/server.crt
chmod 600 /postgres/server.key
chown 999:999 /mongo/server.pem /mongo/ca.pem
chmod 640 /mongo/server.pem
chmod 644 /mongo/ca.pem
chmod 644 /ca/postgres-ca.pem /ca/mongo-ca.pem
rm -rf /tmp/nuam-db-certs
