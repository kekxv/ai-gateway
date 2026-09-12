#!/bin/sh
set -eu

# The MySQL image creates MYSQL_USER with full privileges on MYSQL_DATABASE
# before running files in this directory.  Replace that grant with the CRUD
# privileges required by the long-running gateway.  Migrations and bootstrap
# continue to run as root from the one-shot setup service.
: "${MYSQL_DATABASE:?MYSQL_DATABASE is required}"
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"

case "$MYSQL_DATABASE" in
  *[!A-Za-z0-9_\$-]*|'') echo 'MYSQL_DATABASE contains unsupported identifier characters' >&2; exit 1 ;;
esac
case "$MYSQL_USER" in
  *[!A-Za-z0-9_\$-]*|'') echo 'MYSQL_USER contains unsupported identifier characters' >&2; exit 1 ;;
esac

MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=socket --user=root --database=mysql <<SQL
REVOKE ALL PRIVILEGES, GRANT OPTION FROM \`$MYSQL_USER\`@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`$MYSQL_DATABASE\`.* TO \`$MYSQL_USER\`@'%';
FLUSH PRIVILEGES;
SQL
