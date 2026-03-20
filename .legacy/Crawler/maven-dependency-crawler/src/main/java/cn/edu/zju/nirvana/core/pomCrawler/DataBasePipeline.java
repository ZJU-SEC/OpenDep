package cn.edu.zju.nirvana.core.pomCrawler;

import cn.edu.zju.nirvana.mapper.ArtifactMetaMapper;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import us.codecraft.webmagic.ResultItems;
import us.codecraft.webmagic.Task;
import us.codecraft.webmagic.pipeline.Pipeline;

import java.io.IOException;
import java.io.Reader;
import java.nio.file.Path;
import java.nio.file.Paths;


public class DataBasePipeline implements Pipeline
{

    private Path LocalRepositoryPath;

    SqlSessionFactory sqlSessionFactory;



//    String home = System.getProperty("user.home");
//    java.nio.file.Path path = java.nio.file.Paths.get(home, ".m2", "repository");

    public DataBasePipeline()
    {
        String home = System.getProperty("user.home");
        LocalRepositoryPath =  Paths.get(home, ".m2", "repository");

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

    @Override
    public void process(ResultItems resultItems, Task task)
    {
        String md5 = resultItems.get("md5");
        String pom = resultItems.get("pom");

        try (SqlSession sqlSession = sqlSessionFactory.openSession(true))
        {
            ArtifactMetaMapper artifactMetaMapper = sqlSession.getMapper(ArtifactMetaMapper.class);
            artifactMetaMapper.updatePom(md5, pom);
        }
    }
}