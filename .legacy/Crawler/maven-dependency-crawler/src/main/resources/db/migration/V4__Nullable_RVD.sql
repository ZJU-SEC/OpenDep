alter table "ArtifactMeta"
    drop column rvd;

alter table "ArtifactMeta"
    add rvd boolean default null;