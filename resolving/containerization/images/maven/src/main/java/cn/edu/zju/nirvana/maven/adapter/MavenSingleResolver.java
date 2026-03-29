package cn.edu.zju.nirvana.maven.adapter;

import cn.edu.zju.nirvana.maven.bootstrap.Booter;
import org.eclipse.aether.DefaultRepositorySystemSession;
import org.eclipse.aether.RepositorySystem;
import org.eclipse.aether.artifact.Artifact;
import org.eclipse.aether.artifact.DefaultArtifact;
import org.eclipse.aether.collection.CollectRequest;
import org.eclipse.aether.collection.CollectResult;
import org.eclipse.aether.graph.Dependency;
import org.eclipse.aether.graph.DependencyNode;
import org.eclipse.aether.resolution.ArtifactDescriptorRequest;
import org.eclipse.aether.resolution.ArtifactDescriptorResult;
import org.eclipse.aether.util.graph.manager.DependencyManagerUtils;
import org.eclipse.aether.util.graph.transformer.ConflictResolver;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class MavenSingleResolver {
    private MavenSingleResolver() {
    }

    public static String resolveToJson(String coordinate) throws Exception {
        RepositorySystem system = Booter.newRepositorySystem();
        DefaultRepositorySystemSession session = Booter.newRepositorySystemSession(system);
        session.setConfigProperty(ConflictResolver.CONFIG_PROP_VERBOSE, true);
        session.setConfigProperty(DependencyManagerUtils.CONFIG_PROP_VERBOSE, true);

        Artifact artifact = new DefaultArtifact(coordinate);
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

        LinkedHashMap<String, String> nodes = new LinkedHashMap<String, String>();
        List<String> nodePayloads = new ArrayList<String>();
        List<String> edgePayloads = new ArrayList<String>();
        Set<String> edgeKeys = new LinkedHashSet<String>();

        DependencyNode root = collectResult.getRoot();
        walk(root, null, 0, nodes, nodePayloads, edgePayloads, edgeKeys);

        Artifact rootArtifact = root.getArtifact();
        StringBuilder builder = new StringBuilder();
        builder.append("{");
        builder.append("\"root\":");
        builder.append(nodeJson(rootArtifact, "root"));
        builder.append(",\"nodes\":[");
        appendList(builder, nodePayloads);
        builder.append("],\"edges\":[");
        appendList(builder, edgePayloads);
        builder.append("],\"semantics\":{");
        builder.append("\"source\":\"aether\",");
        builder.append("\"coordinate\":");
        appendJsonString(builder, coordinate);
        builder.append("},\"metrics\":{");
        builder.append("\"node_count\":").append(nodePayloads.size()).append(",");
        builder.append("\"edge_count\":").append(edgePayloads.size());
        builder.append("}}");
        return builder.toString();
    }

    private static void walk(
            DependencyNode current,
            String parentId,
            int depth,
            LinkedHashMap<String, String> nodes,
            List<String> nodePayloads,
            List<String> edgePayloads,
            Set<String> edgeKeys) {
        Artifact artifact = current.getArtifact();
        Dependency dependency = current.getDependency();
        if (artifact == null && dependency != null) {
            artifact = dependency.getArtifact();
        }
        if (artifact == null) {
            return;
        }

        String scope = depth == 0 ? "root" : safeScope(dependency);
        String id = artifactId(artifact);
        if (!nodes.containsKey(id)) {
            nodes.put(id, id);
            nodePayloads.add(nodeJson(artifact, scope));
        }

        if (parentId != null) {
            String edgeKey = parentId + "->" + id;
            if (!edgeKeys.contains(edgeKey)) {
                edgeKeys.add(edgeKey);
                edgePayloads.add(edgeJson(parentId, id, dependency, depth));
            }
        }

        for (DependencyNode child : current.getChildren()) {
            walk(child, id, depth + 1, nodes, nodePayloads, edgePayloads, edgeKeys);
        }
    }

    private static String nodeJson(Artifact artifact, String scope) {
        StringBuilder builder = new StringBuilder();
        builder.append("{");
        builder.append("\"id\":");
        appendJsonString(builder, artifactId(artifact));
        builder.append(",\"ecosystem\":\"maven\",");
        builder.append("\"name\":");
        appendJsonString(builder, artifact.getGroupId() + ":" + artifact.getArtifactId());
        builder.append(",\"version\":");
        appendJsonString(builder, artifact.getVersion());
        builder.append(",\"labels\":{\"scope\":");
        appendJsonString(builder, scope);
        builder.append("},\"attributes\":{\"optional\":false,\"peer\":false,\"dev\":false}}");
        return builder.toString();
    }

    private static String edgeJson(String sourceId, String targetId, Dependency dependency, int depth) {
        StringBuilder builder = new StringBuilder();
        builder.append("{");
        builder.append("\"from\":");
        appendJsonString(builder, sourceId);
        builder.append(",\"to\":");
        appendJsonString(builder, targetId);
        builder.append(",\"type\":");
        appendJsonString(builder, depth == 1 ? "direct" : "transitive");
        builder.append(",\"constraint\":");
        if (dependency != null && dependency.getArtifact() != null) {
            appendJsonString(builder, dependency.getArtifact().getVersion());
        } else {
            builder.append("null");
        }
        builder.append(",\"depth\":").append(depth);
        builder.append(",\"attributes\":{\"optional\":false,\"peer\":false,\"replaced\":false");
        if (dependency != null) {
            builder.append(",\"scope\":");
            appendJsonString(builder, safeScope(dependency));
        }
        builder.append("}}");
        return builder.toString();
    }

    private static String safeScope(Dependency dependency) {
        if (dependency == null || dependency.getScope() == null || dependency.getScope().isEmpty()) {
            return "runtime";
        }
        return dependency.getScope();
    }

    private static String artifactId(Artifact artifact) {
        return "maven:" + artifact.getGroupId() + ":" + artifact.getArtifactId() + "@" + artifact.getVersion();
    }

    private static void appendList(StringBuilder builder, List<String> payloads) {
        for (int i = 0; i < payloads.size(); i++) {
            if (i > 0) {
                builder.append(",");
            }
            builder.append(payloads.get(i));
        }
    }

    private static void appendJsonString(StringBuilder builder, String value) {
        if (value == null) {
            builder.append("null");
            return;
        }
        builder.append('"');
        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);
            switch (current) {
                case '\\':
                    builder.append("\\\\");
                    break;
                case '"':
                    builder.append("\\\"");
                    break;
                case '\n':
                    builder.append("\\n");
                    break;
                case '\r':
                    builder.append("\\r");
                    break;
                case '\t':
                    builder.append("\\t");
                    break;
                default:
                    builder.append(current);
            }
        }
        builder.append('"');
    }
}
