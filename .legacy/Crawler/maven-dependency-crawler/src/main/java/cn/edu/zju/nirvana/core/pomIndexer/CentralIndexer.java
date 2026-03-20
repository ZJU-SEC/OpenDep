package cn.edu.zju.nirvana.core.pomIndexer;

import cn.edu.zju.nirvana.mapper.ArtifactMetaMapper;
import cn.edu.zju.nirvana.models.ArtifactMeta;
import org.apache.commons.io.FileUtils;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.IndexReader;
import org.apache.lucene.store.Directory;
import org.apache.lucene.store.FSDirectory;
import org.apache.maven.index.ArtifactInfo;
import org.apache.maven.index.Indexer;
import org.apache.maven.index.context.IndexCreator;
import org.apache.maven.index.context.IndexUtils;
import org.apache.maven.index.context.IndexingContext;
import org.apache.maven.index.updater.*;
import org.apache.maven.wagon.Wagon;
import org.apache.maven.wagon.events.TransferEvent;
import org.apache.maven.wagon.events.TransferListener;
import org.apache.maven.wagon.observers.AbstractTransferListener;
import org.codehaus.plexus.*;
import org.codehaus.plexus.component.repository.exception.ComponentLookupException;

import java.io.File;
import java.io.IOException;
import java.io.Reader;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;

public class CentralIndexer
{
    private final PlexusContainer plexusContainer;
    private final Indexer indexer;
    private final IndexUpdater indexUpdater;
    private final Wagon httpWagon;

    public CentralIndexer() throws PlexusContainerException, ComponentLookupException
    {
        final DefaultContainerConfiguration defaultContainerConfiguration = new DefaultContainerConfiguration();
        defaultContainerConfiguration.setClassPathScanning(PlexusConstants.SCANNING_INDEX);

        plexusContainer = new DefaultPlexusContainer(defaultContainerConfiguration);

        // lookup the indexer components from plexus
        indexer = plexusContainer.lookup(Indexer.class);
        indexUpdater = plexusContainer.lookup(IndexUpdater.class);

        // lookup wagon used to remotely fetch index
        httpWagon = plexusContainer.lookup(Wagon.class, "http");
    }

    public static void main(String[] args) throws PlexusContainerException, ComponentLookupException, IOException
    {
        CentralIndexer centralIndexer = new CentralIndexer();
        centralIndexer.Sync();
    }

    public void Sync() throws ComponentLookupException, IOException
    {
        // Files where local cache is (if any) and Lucene Index should be located
        File centralIndexDir = FileUtils.getFile(".", "central");

        // Creators we want to use (search for fields it defines)
        List<IndexCreator> indexers = new ArrayList<>();
        indexers.add(plexusContainer.lookup(IndexCreator.class, "min"));
        indexers.add(plexusContainer.lookup(IndexCreator.class, "jarContent"));
        indexers.add(plexusContainer.lookup(IndexCreator.class, "maven-plugin"));

        // Create context for central repository index
        IndexingContext centralContext = indexer.createIndexingContext("central-context", "central", null, centralIndexDir,
                "https://repo.maven.apache.org/maven2", null, true, true, indexers);

        System.out.println("Updating Index...");
        System.out.println("This might take a while on first run, so please be patient");

        // Create ResourceFetcher implementation to be used with IndexUpdateRequest
        // Here, we use Wagon based one as shorthand, but all we need is a ResourceFetcher implementation
        TransferListener listener = new AbstractTransferListener()
        {
            public void transferStarted(TransferEvent transferEvent)
            {
                System.out.print("  Downloading " + transferEvent.getResource().getName());
            }

            public void transferProgress(TransferEvent transferEvent, byte[] buffer, int length)
            {
            }

            public void transferCompleted(TransferEvent transferEvent)
            {
                System.out.println(" - Done");
            }
        };

        ResourceFetcher resourceFetcher = new WagonHelper.WagonFetcher(httpWagon, listener, null, null);
        Date centralContextCurrentTimestamp = centralContext.getTimestamp();
        IndexUpdateRequest updateRequest = new IndexUpdateRequest(centralContext, resourceFetcher);
        IndexUpdateResult updateResult = indexUpdater.fetchAndUpdateIndex(updateRequest);
        if (updateResult.isFullUpdate())
        {
            System.out.println("Full update happened!");
        } else if (updateResult.getTimestamp().equals(centralContextCurrentTimestamp))
        {
            System.out.println("No update needed, index is up to date!");
        } else
        {
            System.out.println(
                    "Incremental update happened, change covered " + centralContextCurrentTimestamp + " - "
                            + updateResult.getTimestamp() + " period.");
        }

        indexer.closeIndexingContext(centralContext, false);

        Directory dir = FSDirectory.open(FileUtils.getFile(".", "central").toPath());
        IndexReader indexReader = DirectoryReader.open(dir);

        final HashSet<ArtifactMeta> artifactMetas = new HashSet<>();

        for (int i = 0; i < indexReader.maxDoc(); i++)
        {
            final Document doc = indexReader.document(i);
            final ArtifactInfo ai = IndexUtils.constructArtifactInfo(doc, centralContext);

            try
            {
                ArtifactMeta artifact = new ArtifactMeta(ai);
                artifactMetas.add(artifact);
            } catch (Exception ignored)
            {
            }
        }

        Reader reader = Resources.getResourceAsReader("mybatis.xml");
        SqlSessionFactory sqlSessionFactory = new SqlSessionFactoryBuilder().build(reader);
        try (SqlSession sqlSession = sqlSessionFactory.openSession(true))
        {
            ArtifactMetaMapper artifactMetaMapper = sqlSession.getMapper(ArtifactMetaMapper.class);

            for (ArtifactMeta artifactMeta : artifactMetas)
            {
                artifactMetaMapper.inertArtifactMeta(artifactMeta);
            }
        }

        File[] tmpFile = centralIndexDir.listFiles();

        assert tmpFile != null;

        for (File f : tmpFile)
        {
            if (!f.getName().endsWith("nexus-maven-repository-index-updater.properties") && !f.getName().endsWith(".keep"))
                f.delete();
        }
    }
}
