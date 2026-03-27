package cn.edu.zju.maven.dependency.resolver.core;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.TimeUnit;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;

public class DependencyTreeGenerateTest {

    private static final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    @DisplayName("Test timeout with simulated long-running operation")
    @Timeout(value = 1, unit = TimeUnit.SECONDS)
    public void testGenerateDependencyTreeJsonTimeout() {
        // Set a very short timeout for testing
        DependencyTreeGenerate.setTimeout(0);

        try {
            // Use special test artifact that will trigger timeout
            String timeoutArtifact = "test:timeout:1.0";

            Exception exception = assertThrows(Exception.class, () -> {
                DependencyTreeGenerate.generateDependencyTreeJson(timeoutArtifact);
            });

            assertTrue(exception instanceof java.util.concurrent.TimeoutException,
                    "Expected TimeoutException but got: " + exception.getClass().getName());
        } finally {
            // Reset timeout to default
            DependencyTreeGenerate.resetTimeout();
        }
    }

    @Test
    @DisplayName("Test valid artifact resolution")
    public void testGenerateDependencyTreeJsonValidArtifact() throws Exception {
        String validArtifact = "org.apache.commons:commons-lang3:3.12.0";

        String result = DependencyTreeGenerate.generateDependencyTreeJson(validArtifact).toString();

        assertNotNull(result);
        assertTrue(result.startsWith("{"));
        assertTrue(result.endsWith("}"));

        // Verify JSON structure
        JsonNode jsonNode = objectMapper.readTree(result);
        assertTrue(jsonNode.isObject(), "Result should be a JSON object");

    }

    @ParameterizedTest
    @DisplayName("Test various valid artifacts")
    @ValueSource(strings = {
            "org.apache.commons:commons-lang3:3.12.0",
            "com.google.guava:guava:31.1-jre",
            "org.slf4j:slf4j-api:2.0.11"
    })
    public void testVariousValidArtifacts(String artifactCoordinate) throws Exception {
        String result = DependencyTreeGenerate.generateDependencyTreeJson(artifactCoordinate).toString();

        assertNotNull(result);
        JsonNode jsonNode = objectMapper.readTree(result);
        assertTrue(jsonNode.isObject(), "Result should be a JSON object");

    }

    @Test
    @DisplayName("Test invalid artifact coordinate format")
    public void testInvalidArtifactCoordinate() {
        String invalidCoordinate = "invalid:format";

        Exception exception = assertThrows(Exception.class, () -> {
            DependencyTreeGenerate.generateDependencyTreeJson(invalidCoordinate);
        });

        assertNotNull(exception.getMessage());
    }

    @Test
    @DisplayName("Test null input")
    public void testNullInput() {
        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            DependencyTreeGenerate.generateDependencyTreeJson(null);
        });

        assertNotNull(exception.getMessage());
    }

    @Test
    @DisplayName("Test empty string input")
    public void testEmptyInput() {
        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            DependencyTreeGenerate.generateDependencyTreeJson("");
        });

        assertNotNull(exception.getMessage());
    }

    @Test
    @DisplayName("Test artifact with no dependencies")
    public void testArtifactWithNoDependencies() throws Exception {
        // Using a simple artifact that typically has no dependencies
        String simpleArtifact = "junit:junit:4.13.2";

        String result = DependencyTreeGenerate.generateDependencyTreeJson(simpleArtifact).toString();

        assertNotNull(result);
        JsonNode jsonNode = objectMapper.readTree(result);
        assertTrue(jsonNode.isObject(), "Result should be a JSON object");
    }
}