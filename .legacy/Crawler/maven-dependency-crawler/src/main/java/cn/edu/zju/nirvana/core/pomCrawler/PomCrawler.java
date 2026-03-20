package cn.edu.zju.nirvana.core.pomCrawler;

import cn.edu.zju.nirvana.mapper.ArtifactMetaMapper;
import cn.edu.zju.nirvana.models.ArtifactMeta;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import us.codecraft.webmagic.Page;
import us.codecraft.webmagic.Request;
import us.codecraft.webmagic.Site;
import us.codecraft.webmagic.Spider;
import us.codecraft.webmagic.processor.PageProcessor;
import us.codecraft.webmagic.utils.HttpConstant;

import java.io.IOException;
import java.io.Reader;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class PomCrawler implements PageProcessor
{
    private static final Set<Integer> DEFAULT_STATUS_CODE_SET = new HashSet<>();

    static
    {
        DEFAULT_STATUS_CODE_SET.add(200);
        DEFAULT_STATUS_CODE_SET.add(404);
    }

    private final Site site = Site.me().setRetrySleepTime(3).setSleepTime(100);


    public PomCrawler()
    {
        site.setCharset("UTF-8");
        site.setAcceptStatCode(DEFAULT_STATUS_CODE_SET);
    }

    public static void crawling() throws IOException
    {
        int CORES = Runtime.getRuntime().availableProcessors();
        ArrayList<Request> reqs = new ArrayList<>();

        Reader reader = Resources.getResourceAsReader("mybatis.xml");
        SqlSessionFactory sqlSessionFactory = new SqlSessionFactoryBuilder().build(reader);

        try (SqlSession sqlSession = sqlSessionFactory.openSession(true))
        {
            ArtifactMetaMapper artifactMetaMapper = sqlSession.getMapper(ArtifactMetaMapper.class);

            List<ArtifactMeta> artifactMetas = artifactMetaMapper.getArtifactMeta2Crawl();

            for (ArtifactMeta artifactMeta : artifactMetas)
            {
                String url = "https://repo.maven.apache.org/maven2/" + String.join("/", artifactMeta.getG().split("\\.")) + "/" + artifactMeta.getA() + "/" + artifactMeta.getV() + "/" + artifactMeta.getA() + "-" + artifactMeta.getV() + ".pom";
                Request req = new Request(url);
                req.putExtra("g", artifactMeta.getG());
                req.putExtra("a", artifactMeta.getA());
                req.putExtra("v", artifactMeta.getV());
                req.putExtra("md5", artifactMeta.getMd5());
                reqs.add(req);
            }

            Spider.create(new PomCrawler()).startRequest(reqs).addPipeline(new DataBasePipeline()).thread(CORES - 2).run();

        }
    }


    public static void main(String[] args) throws IOException
    {
        PomCrawler.crawling();
    }

    @Override
    public void process(Page page)
    {
        String g = page.getRequest().getExtra("g");
        String a = page.getRequest().getExtra("a");
        String v = page.getRequest().getExtra("v");
        String md5 = page.getRequest().getExtra("md5");

        String pom = String.format(
                "<project> " +
                        "<modelVersion>4.0.0</modelVersion> " +
                        "<groupId>%s</groupId>" +
                        "<artifactId>%s</artifactId>" +
                        "<version>%s</version>" +
                        "</project>",
                g, a, v
        );

        if (page.getStatusCode() == HttpConstant.StatusCode.CODE_200)
        {
            pom = page.getRawText();
        }

        page.putField("md5", md5);
        page.putField("pom", pom);
    }

    @Override
    public Site getSite()
    {
        return site;
    }
}