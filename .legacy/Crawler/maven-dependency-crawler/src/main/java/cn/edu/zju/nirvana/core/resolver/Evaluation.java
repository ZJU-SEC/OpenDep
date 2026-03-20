package cn.edu.zju.nirvana.core.resolver;

import cn.edu.zju.nirvana.core.resolver.util.Booter;
import org.apache.ibatis.io.Resources;
import org.eclipse.aether.DefaultRepositorySystemSession;
import org.eclipse.aether.RepositorySystem;
import org.eclipse.aether.artifact.Artifact;
import org.eclipse.aether.artifact.DefaultArtifact;
import org.eclipse.aether.collection.CollectRequest;
import org.eclipse.aether.collection.CollectResult;
import org.eclipse.aether.collection.DependencyCollectionException;
import org.eclipse.aether.graph.DependencyNode;
import org.eclipse.aether.resolution.ArtifactDescriptorException;
import org.eclipse.aether.resolution.ArtifactDescriptorRequest;
import org.eclipse.aether.resolution.ArtifactDescriptorResult;
import org.eclipse.aether.util.graph.manager.DependencyManagerUtils;
import org.eclipse.aether.util.graph.transformer.ConflictResolver;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import java.io.*;
import java.util.ArrayList;
import java.util.List;

public class Evaluation {
    private final static int CORES = 250;

    private static List<String> JOBS = new ArrayList<String>();

    private static class Resolving implements Runnable {
        private List<String> jobs;
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

        public Resolving(int thread_id, List<String> jobs) {
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

            for (String info : jobs) {
                try {
                    Artifact artifact = new DefaultArtifact(info);

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

                    try (FileWriter fileWriter = new FileWriter("/home/cnspary/project/evaluation/maven/BenchMark/"+info+".xml")) {

                        fileWriter.write(xmlString);
                        System.out.println("String written to file successfully!");

                    } catch (IOException e) {
                        e.printStackTrace();
                    }
                } catch (Exception ignore) {
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

    public static void main( String[] args ) throws ArtifactDescriptorException, DependencyCollectionException, ParserConfigurationException, TransformerException {
        // fill JOBS through read file
        String fileName = "/home/cnspary/project/evaluation/maven/Top5k";

        try (BufferedReader br = new BufferedReader(new FileReader(fileName))) {
            String line;

            while ((line = br.readLine()) != null) {
                JOBS.add(line);
            }
        } catch (IOException e) {
            System.err.println("Error reading the file: " + e.getMessage());
        }

        int jobPerCore = 20;

        ArrayList<Thread> threads = new ArrayList<>();

        int bound = Math.min(CORES, JOBS.size());

        for (int i = 1; i <= 250; ++i) {
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
