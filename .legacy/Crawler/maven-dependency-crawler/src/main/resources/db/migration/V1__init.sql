create table public."ArtifactMeta"
(
    md5      char(32)              not null
        constraint table_name_pk
            primary key,
    g        varchar(128)          not null,
    a        varchar(128)          not null,
    v        varchar(128)          not null,
    describe text,
    ts       timestamp             not null,
    hrd      boolean default false not null,
    resolved boolean default false not null,
    deptree  xml
);