```epic
title: minidb — SQL database engine in Python
branch: none
worktree: false

description:
Build "minidb" — a minimal but functional SQL database engine in pure Python.
The project lives in apps/minidb/ within the working directory.

Architecture (each is a separate module):

  minidb/
    __init__.py
    tokenizer.py    — SQL tokenizer (keywords, identifiers, literals, operators)
    parser.py       — Recursive descent parser → AST nodes
    ast_nodes.py    — Dataclass AST: CreateTable, Insert, Select, Update, Delete, Drop
    schema.py       — Table schema registry (column names, types, constraints)
    storage.py      — Row storage engine with JSON file persistence per table
    indexing.py     — B-tree index for fast lookups on indexed columns
    executor.py     — Query executor: walks AST, calls storage/index
    planner.py      — Simple query planner: chooses index scan vs full scan
    transactions.py — Transaction manager: BEGIN/COMMIT/ROLLBACK with WAL
    functions.py    — Built-in functions: COUNT, SUM, AVG, MIN, MAX, UPPER, LOWER
    repl.py         — Interactive REPL with readline support
    cli.py          — CLI entry point: repl mode + file execution mode
  tests/
    test_tokenizer.py
    test_parser.py
    test_storage.py
    test_indexing.py
    test_executor.py
    test_transactions.py
    test_integration.py

Supported SQL subset:
  CREATE TABLE name (col1 TYPE, col2 TYPE, ...)
  DROP TABLE name
  INSERT INTO name (cols...) VALUES (vals...), (vals...), ...
  SELECT cols FROM table [WHERE cond] [ORDER BY col ASC|DESC] [LIMIT n]
  SELECT with JOIN: SELECT ... FROM t1 JOIN t2 ON t1.col = t2.col
  UPDATE table SET col=val [WHERE cond]
  DELETE FROM table [WHERE cond]
  BEGIN / COMMIT / ROLLBACK

Supported types: INTEGER, TEXT, REAL, BOOLEAN
Supported WHERE operators: =, !=, <, >, <=, >=, AND, OR, NOT, IS NULL, IS NOT NULL, LIKE
Supported aggregates: COUNT(*), COUNT(col), SUM, AVG, MIN, MAX
GROUP BY and HAVING support

Storage:
  - Each table stored as a JSON file in a data directory
  - WAL (write-ahead log) for transaction safety
  - B-tree index stored as separate JSON file per indexed column
  - CREATE INDEX name ON table(column)

REPL:
  - Readline with history
  - Multi-line input (until semicolon)
  - Pretty-printed table output with column alignment
  - .tables, .schema, .quit meta-commands

acceptance:
- Tokenizer correctly handles all SQL keywords, string literals (with escapes), numbers, identifiers
- Parser produces correct AST for all supported SQL statements
- CREATE TABLE / DROP TABLE work with schema validation
- INSERT supports single and multi-row inserts
- SELECT works with WHERE, ORDER BY, LIMIT, JOIN
- UPDATE and DELETE work with WHERE clauses
- GROUP BY with aggregate functions produces correct results
- B-tree index speeds up equality lookups (CREATE INDEX / automatic use in WHERE)
- Transactions: BEGIN starts transaction, COMMIT persists, ROLLBACK reverts all changes
- WAL ensures crash safety — uncommitted changes don't corrupt data
- REPL handles multi-line input, meta-commands, and pretty-prints results
- All tests pass: python3 -m pytest tests/ -v
- At least 50 test cases covering tokenizer, parser, storage, indexing, executor, transactions

checks:
- test: cd {workdir}/apps/minidb && python3 -m pytest tests/ -v
```
