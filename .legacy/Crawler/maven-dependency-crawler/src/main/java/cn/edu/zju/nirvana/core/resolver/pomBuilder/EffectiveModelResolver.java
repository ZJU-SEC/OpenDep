package cn.edu.zju.nirvana.core.resolver.pomBuilder;

import cn.edu.zju.nirvana.core.resolver.util.PomUtils;
import cn.edu.zju.nirvana.mapper.ArtifactMetaMapper;
import cn.edu.zju.nirvana.models.ArtifactMeta;
import org.apache.commons.codec.digest.DigestUtils;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.maven.model.Dependency;
import org.apache.maven.model.Parent;
import org.apache.maven.model.Repository;
import org.apache.maven.model.building.ModelSource;
import org.apache.maven.model.building.StringModelSource;
import org.apache.maven.model.resolution.InvalidRepositoryException;
import org.apache.maven.model.resolution.ModelResolver;
import org.apache.maven.model.resolution.UnresolvableModelException;

import java.io.IOException;
import java.io.Reader;

public class EffectiveModelResolver implements ModelResolver
{
    private static final SqlSessionFactory sqlSessionFactory;

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
    @Override
    public ModelSource resolveModel(String groupId, String artifactId, String version) throws UnresolvableModelException
    {
        try (SqlSession sqlSession = sqlSessionFactory.openSession(true))
        {
            ArtifactMetaMapper artifactMetaMapper = sqlSession.getMapper(ArtifactMetaMapper.class);
            ArtifactMeta artifactMeta = artifactMetaMapper.getByMd5(DigestUtils.md5Hex(groupId + ":" + artifactId + ":" + version).toUpperCase());
            if (artifactMeta == null)
                return new StringModelSource(PomUtils.DefaultPom(groupId, artifactId, version));
            return new StringModelSource(artifactMeta.getPom());
        }
    }

    public ModelSource resolveModel(Parent parent) throws UnresolvableModelException
    {
        return resolveModel(parent.getGroupId(), parent.getArtifactId(), parent.getVersion());
    }

    public ModelSource resolveModel(Dependency dependency) throws UnresolvableModelException {
        return null;
    }

    @Override
    public void addRepository(Repository repository) throws InvalidRepositoryException {

    }

    public void addRepository(Repository repository, boolean replace) throws InvalidRepositoryException {

    }

    @Override
    public ModelResolver newCopy() {
        return null;
    }
}