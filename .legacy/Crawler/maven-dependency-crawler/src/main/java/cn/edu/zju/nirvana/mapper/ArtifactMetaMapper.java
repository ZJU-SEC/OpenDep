package cn.edu.zju.nirvana.mapper;

import cn.edu.zju.nirvana.models.ArtifactMeta;
import org.apache.ibatis.annotations.Param;

import java.util.List;


public interface ArtifactMetaMapper {

    // Basic
    void inertArtifactMeta(ArtifactMeta artifactMeta);

    ArtifactMeta getByMd5(@Param("md5") String md5);

    List<ArtifactMeta> getArtifactMeta2Crawl();
    List<ArtifactMeta> getPom2Disk();
    List<ArtifactMeta> getArtifact2RVD();
    List<ArtifactMeta> getArtifact2Deptree();

    void updatePom(@Param("md5") String md5, @Param("pom")String pom);
    void updateDisk(@Param("md5") String md5);
    void updateRVD(@Param("md5") String md5, @Param("rvd") Boolean rvd);
    void updateDepTree(@Param("md5") String md5, @Param("deptree")String deptree);

}
