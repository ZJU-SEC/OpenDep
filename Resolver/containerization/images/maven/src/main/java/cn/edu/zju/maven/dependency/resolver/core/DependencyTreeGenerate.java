package cn.edu.zju.maven.dependency.resolver.core;

import cn.edu.zju.maven.dependency.resolver.core.utils.Booter;
import org.eclipse.aether.RepositorySystem;
import org.eclipse.aether.DefaultRepositorySystemSession;
import org.eclipse.aether.artifact.Artifact;
import org.eclipse.aether.artifact.DefaultArtifact;
import org.eclipse.aether.collection.CollectRequest;
import org.eclipse.aether.collection.CollectResult;
import org.eclipse.aether.graph.Dependency;
import org.eclipse.aether.graph.DependencyNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.JsonNode;

import cn.edu.zju.maven.dependency.resolver.core.utils.Pair;
import java.util.Queue;
import java.util.LinkedList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.Executors;

/**
 * Collects the transitive dependencies of an artifact.
 */
public class DependencyTreeGenerate {

    private static final long DEFAULT_TIMEOUT = 3;
    private static TimeUnit DEFAULT_TIMEOUT_UNIT = TimeUnit.MINUTES;
    private static long timeout = DEFAULT_TIMEOUT;
    private static TimeUnit timeoutUnit = DEFAULT_TIMEOUT_UNIT;

    public static void setTimeout(long t) {
        timeout = t;
        timeoutUnit = TimeUnit.SECONDS;
    }

    public static void resetTimeout() {
        timeout = DEFAULT_TIMEOUT;
        timeoutUnit = DEFAULT_TIMEOUT_UNIT;
    }

    private static JsonNode dependencyTreeToJson(DependencyNode root) {
        ObjectMapper objectMapper = new ObjectMapper();
        ObjectNode finalRootJson = objectMapper.createObjectNode();

        // The queue now holds: (original DependencyNode, its parent's ObjectNode in the
        // JSON structure)
        Queue<Pair<DependencyNode, ObjectNode>> queue = new LinkedList<>();

        // Initialize BFS:
        // The root DependencyNode "Node" will be placed directly into 'finalRootJson'.
        // Its initial parent in the JSON structure is 'finalRootJson' itself.
        queue.add(new Pair<>(root, finalRootJson));

        while (!queue.isEmpty()) {
            Pair<DependencyNode, ObjectNode> currentPair = queue.poll();

            DependencyNode currentNode = currentPair.getKey();
            ObjectNode parentJsonObject = currentPair.getValue();

            String nodeKey = currentNode.getArtifact().getGroupId() + ":" + currentNode.getArtifact().getArtifactId()
                    + ":" + currentNode.getArtifact().getVersion();

            // Create a new empty JSON object for the current node.
            // This object will either contain its children as keys, or be empty if it's a
            // leaf.
            ObjectNode currentJsonObject = objectMapper.createObjectNode();

            // Add the current node's JSON object as a property of its parent's JSON object.
            // The key is the node's artifact name.
            parentJsonObject.set(nodeKey, currentJsonObject);

            for (DependencyNode childNode : currentNode.getChildren()) {
                queue.add(new Pair<>(childNode, currentJsonObject));
            }
        }

        return finalRootJson;
    }

    /**
     * Wrapper method to generate dependency tree JSON from a Maven artifact
     * coordinate.
     * 
     * @param artifactCoordinate The Maven artifact coordinate in format
     *                           "groupId:artifactId:version"
     * @return JSON string representation of the dependency tree
     * @throws Exception if there's an error resolving dependencies or generating
     *                   JSON
     */
    public static JsonNode generateDependencyTreeJson(String artifactCoordinate) throws Exception {
        // Input validation
        if (artifactCoordinate == null) {
            throw new IllegalArgumentException("Artifact coordinate cannot be null");
        }
        if (artifactCoordinate.trim().isEmpty()) {
            throw new IllegalArgumentException("Artifact coordinate cannot be empty");
        }

        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<JsonNode> future = executor.submit(() -> {
            RepositorySystem system = Booter.newRepositorySystem();
            DefaultRepositorySystemSession session = Booter.newRepositorySystemSession(system);

            Artifact artifact = new DefaultArtifact(artifactCoordinate);

            CollectRequest collectRequest = new CollectRequest();
            collectRequest.setRoot(new Dependency(artifact, ""));
            collectRequest.setRepositories(Booter.newRepositories(system, session));

            CollectResult collectResult = system.collectDependencies(session, collectRequest);
            return dependencyTreeToJson(collectResult.getRoot());
        });

        try {
            return future.get(timeout, timeoutUnit);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new TimeoutException(
                    "Resolving timed out after " + timeout + " " + timeoutUnit.toString());
        } catch (Exception e) {
            future.cancel(true);
            throw new Exception("Resolving failed: " + e.getMessage());
        } finally {
            executor.shutdownNow();
        }
    }
}