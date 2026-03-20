package cn.edu.zju.maven.dependency.resolver.core;

import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.FileWriter;
import java.io.IOException;

/**
 * Simplified single-threaded dependency resolver
 * Processes one Maven artifact coordinate at a time, generating the corresponding dependency tree
 */
public class SimpleDependencyResolver {
    private static final Logger logger = LoggerFactory.getLogger(SimpleDependencyResolver.class);

    /**
     * Resolve dependency tree for a single Maven artifact and return in JSON format
     * 
     * @param coordinate Maven artifact coordinate (groupId:artifactId:version)
     * @return JSON representation of the dependency tree
     * @throws Exception if an error occurs during resolution
     */
    public static JsonNode resolveDependencyTree(String coordinate) throws Exception {
        logger.info("Starting resolving: {}", coordinate);
        
        try {
            JsonNode dependencyTree = DependencyTreeGenerate.generateDependencyTreeJson(coordinate);
            logger.info("Successfully resolved: {}", coordinate);
            return dependencyTree;
        } catch (Exception e) {
            logger.error("Failed to resolve: {} - {}", coordinate, e.getMessage());
            throw e;
        }
    }

    /**
     * Resolve dependency tree and print to console
     * 
     * @param coordinate Maven artifact coordinate
     * @throws Exception if an error occurs during resolution
     */
    public static void resolveDependencyTreeAndPrint(String coordinate) throws Exception {
        JsonNode dependencyTree = resolveDependencyTree(coordinate);
        System.out.println("Resolving for " + coordinate + ":");
        System.out.println("================");
        System.out.println(dependencyTree.toPrettyString());
    }

    /**
     * Resolve dependency tree and save to file
     * 
     * @param coordinate Maven artifact coordinate
     * @param outputFile Output file path
     * @throws Exception if an error occurs during resolution or file writing
     */
    public static void resolveDependencyTreeAndSave(String coordinate, String outputFile) throws Exception {
        JsonNode dependencyTree = resolveDependencyTree(coordinate);
        
        try (FileWriter writer = new FileWriter(outputFile)) {
            writer.write(dependencyTree.toPrettyString());
            logger.info("Resolving saved to file: {}", outputFile);
        } catch (IOException e) {
            logger.error("Failed to write file: {} - {}", outputFile, e.getMessage());
            throw new Exception("Unable to write output file: " + e.getMessage(), e);
        }
    }

    /**
     * Set dependency resolution timeout
     * 
     * @param timeoutSeconds Timeout in seconds
     */
    public static void setTimeout(long timeoutSeconds) {
        DependencyTreeGenerate.setTimeout(timeoutSeconds);
        logger.info("Set resolving timeout: {} seconds", timeoutSeconds);
    }

    /**
     * Reset timeout to default value
     */
    public static void resetTimeout() {
        DependencyTreeGenerate.resetTimeout();
        logger.info("Reset resolving timeout to default value");
    }
}