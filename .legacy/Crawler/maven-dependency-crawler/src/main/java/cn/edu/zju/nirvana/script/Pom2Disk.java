package cn.edu.zju.nirvana.script;

import cn.edu.zju.nirvana.core.resolver.GetDependencyHierarchy;

import cn.edu.zju.nirvana.mapper.ArtifactMetaMapper;
import cn.edu.zju.nirvana.models.ArtifactMeta;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.log4j.Logger;


import java.io.IOException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

public class Pom2Disk {

    private static final SqlSessionFactory sqlSessionFactory;

    private static final Logger LOGGER = Logger.getLogger(GetDependencyHierarchy.class);

    static
    {

        Reader reader = null;
        try
        {
            reader = Resources.getResourceAsReader("mybatis.xml");
        } catch (IOException e)
        {
            e.printStackTrace();
        }
        sqlSessionFactory = new SqlSessionFactoryBuilder().build(reader);
    }


    private static String LocalRepository = Paths.get(System.getProperty("user.home"), ".m2", "repository").toString();
    public static void main( String[] args )
    {
        try (SqlSession sqlSession = sqlSessionFactory.openSession(true)) {

            while (true) {
                ArtifactMetaMapper artifactMetaMapper = sqlSession.getMapper(ArtifactMetaMapper.class);
                List<ArtifactMeta> artifactMetaList = artifactMetaMapper.getPom2Disk();

                if (artifactMetaList.size() == 0) {
                    break;
                }

                for (ArtifactMeta artifactMeta : artifactMetaList) {
                    String g = artifactMeta.getG();
                    String a = artifactMeta.getA();
                    String v = artifactMeta.getV();

                    Path filePath = Paths.get(LocalRepository,
                            String.join("/", g.split("\\.")),
                            a,
                            v
                    );

                    Path file = Paths.get(filePath.toString(), a + "-" + v + ".pom");

                    try {
                        Files.createDirectories(filePath);
                    } catch (Exception ignore) {

                    }

                    try {
                        Files.writeString(file, artifactMeta.getPom());
                    } catch (Exception e) {
                        LOGGER.error("Failed to write pom to file [" + g + ":" + a + ": " + v + "]");
                    }

                    artifactMetaMapper.updateDisk(artifactMeta.getMd5());

                }
            }
        }
    }
}
