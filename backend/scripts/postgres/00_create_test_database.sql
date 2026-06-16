-- Create the integration-test database (run connected to postgres DB).
-- Override: psql -v test_db_name=ecotwin_test -v db_user=ecotwin ...

\set test_db_name ecotwin_test
\set db_user ecotwin

SELECT format('CREATE DATABASE %I OWNER %I', :'test_db_name', :'db_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'test_db_name')
\gexec
