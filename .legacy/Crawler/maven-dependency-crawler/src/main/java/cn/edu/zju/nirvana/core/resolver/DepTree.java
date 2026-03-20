package cn.edu.zju.nirvana.core.resolver;

import cn.edu.zju.nirvana.core.resolver.util.Booter;
import cn.edu.zju.nirvana.core.resolver.util.ConsoleDependencyGraphDumper;
import cn.edu.zju.nirvana.mapper.ArtifactMetaMapper;
import cn.edu.zju.nirvana.models.ArtifactMeta;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
// import org.apache.log4j.Logger;
import org.eclipse.aether.DefaultRepositorySystemSession;
import org.eclipse.aether.RepositorySystem;
import org.eclipse.aether.RepositorySystemSession;
import org.eclipse.aether.artifact.Artifact;
import org.eclipse.aether.artifact.DefaultArtifact;
import org.eclipse.aether.collection.CollectRequest;
import org.eclipse.aether.collection.CollectResult;
import org.eclipse.aether.collection.DependencyCollectionException;
import org.eclipse.aether.graph.Dependency;
import org.eclipse.aether.graph.DependencyNode;
import org.eclipse.aether.resolution.ArtifactDescriptorException;
import org.eclipse.aether.resolution.ArtifactDescriptorRequest;
import org.eclipse.aether.resolution.ArtifactDescriptorResult;
import org.eclipse.aether.util.graph.manager.DependencyManagerUtils;
import org.eclipse.aether.util.graph.transformer.ConflictResolver;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

import java.io.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import java.io.IOException;
import java.io.Reader;
import java.io.StringWriter;
import java.sql.Array;
import java.util.ArrayList;
import java.util.List;

public class DepTree {
    // private static final Logger LOGGER = Logger.getLogger(DepTree.class);

    private final static int CORES = 30;

    private static List<String[]> JOBS = new ArrayList<>();

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

    private static class Resolving implements Runnable {
        private List<String[]> jobs;
        private int thread_id;

        private static final String DEFAULT_XML = "<?xml version=\"1.0\" standalone=\"no\"?>";


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
//            sqlSessionFactory = new SqlSessionFactoryBuilder().build(reader);
        }

        public Resolving(int thread_id, List<String[]> jobs) {
            this.thread_id = thread_id;
            this.jobs = jobs;
        }

        public static void main(String[] args) throws DependencyCollectionException, ArtifactDescriptorException, ParserConfigurationException, TransformerException {
            RepositorySystem system = Booter.newRepositorySystem();
            DefaultRepositorySystemSession session = Booter.newRepositorySystemSession( system );

            session.setConfigProperty( ConflictResolver.CONFIG_PROP_VERBOSE, true );
            session.setConfigProperty( DependencyManagerUtils.CONFIG_PROP_VERBOSE, true );

            Artifact artifact = new DefaultArtifact("org.beangle.data:beangle-data-orm_3:5.4.0");

            ArtifactDescriptorRequest descriptorRequest = new ArtifactDescriptorRequest();
            descriptorRequest.setArtifact(artifact);
            descriptorRequest.setRepositories(Booter.newRepositories(system, session));

            ArtifactDescriptorResult descriptorResult = system.readArtifactDescriptor(session, descriptorRequest);

            CollectRequest collectRequest = new CollectRequest();
            collectRequest.setRootArtifact(descriptorResult.getArtifact());
            collectRequest.setDependencies(descriptorResult.getDependencies());
            collectRequest.setManagedDependencies(descriptorResult.getManagedDependencies());
            collectRequest.setRepositories(descriptorRequest.getRepositories());

            CollectResult collectResult = system.collectDependencies(session, collectRequest);

            String xmlString = getDepTreeXML(collectResult);

            System.out.println(xmlString);

        }

        @Override
        public void run() {
            RepositorySystem system = Booter.newRepositorySystem();
            DefaultRepositorySystemSession session = Booter.newRepositorySystemSession( system );

            session.setConfigProperty( ConflictResolver.CONFIG_PROP_VERBOSE, true );
            session.setConfigProperty( DependencyManagerUtils.CONFIG_PROP_VERBOSE, true );

            try (SqlSession sqlSession = sqlSessionFactory.openSession(true)) {
                ArtifactMetaMapper artifactMetaMapper = sqlSession.getMapper(ArtifactMetaMapper.class);
                for (String[] info : jobs) {
                    try {
                        Artifact artifact = new DefaultArtifact(info[1]);

                        ArtifactDescriptorRequest descriptorRequest = new ArtifactDescriptorRequest();
                        descriptorRequest.setArtifact(artifact);
                        descriptorRequest.setRepositories(Booter.newRepositories(system, session));

                        ArtifactDescriptorResult descriptorResult = system.readArtifactDescriptor(session, descriptorRequest);

                        CollectRequest collectRequest = new CollectRequest();
                        collectRequest.setRootArtifact(descriptorResult.getArtifact());
                        collectRequest.setDependencies(descriptorResult.getDependencies());
                        collectRequest.setManagedDependencies(descriptorResult.getManagedDependencies());
                        collectRequest.setRepositories(descriptorRequest.getRepositories());

                        CollectResult collectResult = system.collectDependencies(session, collectRequest);

                   //   boolean rvd = isRvd(descriptorResult);
                   //   artifactMetaMapper.updateRVD(info[0], rvd);

                        String xmlString = getDepTreeXML(collectResult);
                        artifactMetaMapper.updateDepTree(info[0], xmlString);
                    } catch (Exception ignore) {
                        artifactMetaMapper.updateDepTree(info[0], DEFAULT_XML);
                        // LOGGER.error(info[1]);
                    }
                }
            }

        }

        private static String getDepTreeXML(CollectResult collectResult) throws ParserConfigurationException, TransformerException {
            DocumentBuilderFactory docFactory = DocumentBuilderFactory.newInstance();
            DocumentBuilder docBuilder = docFactory.newDocumentBuilder();

            Document doc = docBuilder.newDocument();
            Element root = doc.createElement("artifact");
            String arti =  collectResult.getRoot().getArtifact().getGroupId() +":"
                    + collectResult.getRoot().getArtifact().getArtifactId() +":"
                    + collectResult.getRoot().getArtifact().getVersion();
            root.setAttribute("id", arti);
            root.setIdAttribute("id", true);
            doc.appendChild(root);

            for (DependencyNode child : collectResult.getRoot().getChildren()) {
                if (child.getDependency().getScope().equals("test"))
                    continue;
                Resolving.dependencyGraphDumper(doc, root, child);
            }

            TransformerFactory tf = TransformerFactory.newInstance();
            Transformer transformer;

            transformer = tf.newTransformer();

            // Uncomment if you do not require XML declaration
            // transformer.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "yes");

            //A character stream that collects its output in a string buffer,
            //which can then be used to construct a string.
            StringWriter writer = new StringWriter();

            //transform document to string
            transformer.transform(new DOMSource(doc), new StreamResult(writer));

            String xmlString = writer.getBuffer().toString();

            return xmlString;
        }

        private static boolean isRvd(ArtifactDescriptorResult descriptorResult) {
            boolean rvd = false;

            for (Dependency dependency : descriptorResult.getDependencies()) {
                if (dependency.getScope().equals("test"))
                    continue;

                if (dependency.getArtifact().getVersion().startsWith("(") || dependency.getArtifact().getVersion().startsWith("[")) {
                    rvd = true;
                    break;
                }
            }
            return rvd;
        }

        private static class DepInfo {
            private String from;
            private String to;
            private String scope;
            private Boolean optional;

            public DepInfo(String from, String to, String scope, Boolean optional) {
                this.from = from;
                this.to = to;
                this.scope = scope;
                this.optional = optional;
            }

            public String getFrom() {
                return from;
            }

            public void setFrom(String from) {
                this.from = from;
            }

            public String getTo() {
                return to;
            }

            public void setTo(String to) {
                this.to = to;
            }

            public String getScope() {
                return scope;
            }

            public void setScope(String scope) {
                this.scope = scope;
            }

            public String getOptional() {
                return String.valueOf(optional);
            }

            public void setOptional(Boolean optional) {
                this.optional = optional;
            }
        }

        public static String formatNode(DependencyNode node) {
            String buffer = node.getArtifact().getGroupId() +
                    ":" +
                    node.getArtifact().getArtifactId() +
                    ":" +
                    node.getArtifact().getVersion();
            return buffer;
        }

        public static void dependencyGraphDumper(Document doc, Element parentElement, DependencyNode child) {
            Element cElement = doc.createElement("dependency");
            cElement.setAttribute("id", formatNode(child));
            cElement.setAttribute("scope", child.getDependency().getScope());
            cElement.setAttribute("optional", child.getDependency().getOptional().toString());
            cElement.setIdAttribute("id", true);
            parentElement.appendChild(cElement);

            for (DependencyNode grandson : child.getChildren()) {
                if (grandson.getDependency().getScope().equals("test"))
                    continue;
                dependencyGraphDumper(doc, cElement, grandson);
            }
        }
    }

    public static void Run() {
        try (SqlSession sqlSession = sqlSessionFactory.openSession(true)) {
            ArtifactMetaMapper artifactMetaMapper = sqlSession.getMapper(ArtifactMetaMapper.class);
            List<ArtifactMeta> artifactMetaList = artifactMetaMapper.getArtifact2Deptree();

            for (ArtifactMeta artifactMeta: artifactMetaList) {
                String[] job = {artifactMeta.getMd5(), artifactMeta.getG()+":"+artifactMeta.getA()+":"+artifactMeta.getV()};
                JOBS.add(job);
            }

            int jobPerCore = JOBS.size() / CORES;

            ArrayList<Thread> threads = new ArrayList<>();

            for (int i = 1; i < CORES; ++i) {
                int start = jobPerCore * (i-1);
                int end = jobPerCore * i;
                Runnable r = new Resolving(i, JOBS.subList(start, end));
                threads.add(new Thread(r));
            }

            Runnable r = new Resolving(CORES, JOBS.subList(jobPerCore * (CORES-1), JOBS.size()));
            threads.add(new Thread(r));

            for (int i = 0 ; i < CORES; ++i) {
                threads.get(i).start();
            }

            for (int i = 0; i < CORES; ++i) {
                try {
                    threads.get(i).join();
                } catch (InterruptedException e) {
                }
            }
        }
    }

    public static void main( String[] args ) throws ArtifactDescriptorException, DependencyCollectionException, ParserConfigurationException, TransformerException {
        // System.out.println( "------------------------------------------------------------" );
        // System.out.println( GetDependencyHierarchy.class.getSimpleName() );

        RepositorySystem system = Booter.newRepositorySystem();

        DefaultRepositorySystemSession session = Booter.newRepositorySystemSession( system );

        session.setConfigProperty( ConflictResolver.CONFIG_PROP_VERBOSE, true );
        session.setConfigProperty( DependencyManagerUtils.CONFIG_PROP_VERBOSE, true );

        String Input = args[0];

        Artifact artifact = new DefaultArtifact( Input );

        ArtifactDescriptorRequest descriptorRequest = new ArtifactDescriptorRequest();
        descriptorRequest.setArtifact( artifact );
        descriptorRequest.setRepositories( Booter.newRepositories( system, session ) );

        ArtifactDescriptorResult descriptorResult = system.readArtifactDescriptor( session, descriptorRequest );

        CollectRequest collectRequest = new CollectRequest();
        collectRequest.setRootArtifact( descriptorResult.getArtifact() );
        collectRequest.setDependencies( descriptorResult.getDependencies() );
        collectRequest.setManagedDependencies( descriptorResult.getManagedDependencies() );
        collectRequest.setRepositories( descriptorRequest.getRepositories() );

        CollectResult collectResult = system.collectDependencies(session, collectRequest);

        // collectResult.getRoot().accept( new ConsoleDependencyGraphDumper() );
        String xmlString = Resolving.getDepTreeXML(collectResult);

        String FilePath = String.format("./.BenchMark-New/%s.xml", Input);
        Path path = Paths.get(FilePath);

        try {
            // Now calling Files.writeString() method
            // with path , content & standard charsets
            Files.writeString(path, xmlString,
                              StandardCharsets.UTF_8);
        }
 
        // Catch block to handle the exception
        catch (IOException ex) {
            // Print messqage exception occurred as
            // invalid. directory local path is passed
            System.out.print("Invalid Path");
        }
    }
}
