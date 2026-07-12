# PostgreSQL + PostGIS + pgvector Setup Guide (Ubuntu)

## 0. Install PostgreSQL

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib -y

psql --version
```

---

## 1. Install PostGIS

> **Note:** Replace `14` with your PostgreSQL version if required.

```bash
sudo apt install postgresql-14-postgis-3 postgresql-14-postgis-3-scripts -y
```

---

## 2. Install PostgreSQL Development Headers

These are required to build **pgvector**.

```bash
sudo apt install postgresql-server-dev-14 build-essential git -y
```

---

## 3. Install pgvector

```bash
git clone https://github.com/pgvector/pgvector.git

cd pgvector

make

sudo make install
```

---

## 4. Create Database & Enable Extensions

Open PostgreSQL:

```bash
sudo -u postgres psql
```

Create the database:

```sql
CREATE DATABASE ecotwin;
```

Connect to the database:

```sql
\c ecotwin
```

Enable the required extensions:

```sql
CREATE EXTENSION postgis;
CREATE EXTENSION vector;
```

Verify installation:

```sql
\dx
```

---

## 5. Install PgAdmin

Install PgAdmin using your preferred installation method.

---

## 6. Configure PgAdmin

Open **PgAdmin**.

### Login

| Field | Value |
|-------|-------|
| Email | `admin@example.com` |
| Password | `admin123` |

---

### Add New Server

Right click **Servers** → **Register** → **Server**

#### General

| Field | Value |
|-------|-------|
| Name | `Local PostgreSQL` |

#### Connection

| Field | Value |
|-------|-------|
| Host Name/Address | `localhost` |
| Port | `5432` |
| Maintenance Database | `postgres` |
| Username | Check your `.env` file |
| Password | Check your `.env` file |

Save the server.

---

## 7. Run Database Migrations

Navigate to the backend project.

Run:

```bash
alembic upgrade head
```

---

## Verification

The following should work successfully:

- PostgreSQL installed
- PostGIS extension enabled
- pgvector extension enabled
- PgAdmin connected to the local database
- `alembic upgrade head` completes without errors