-- Run as PostgreSQL superuser (e.g. psql -U postgres -f 00_create_role_and_database.sql)
-- Creates the application role and primary database.
-- Override defaults via psql variables:  psql -v db_name=ecotwin -v db_user=ecotwin ...

\set db_name ecotwin
\set db_user ecotwin
-- Set password before running:  psql -v db_password="'your_password'" ...
\if :{?db_password}
\else
\set db_password '''changeme'''
\endif

SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %s', :'db_user', :'db_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'db_user')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name')
\gexec

GRANT ALL PRIVILEGES ON DATABASE :"db_name" TO :"db_user";
