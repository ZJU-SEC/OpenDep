package cn.edu.zju.nirvana.maven.adapter;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class MavenSingleResolverTest {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    @Test
    @DisplayName("Resolve JSON graph for a valid Maven coordinate")
    public void testResolveToJsonValidArtifact() throws Exception {
        String coordinate = "org.apache.commons:commons-lang3:3.12.0";

        String payload = MavenSingleResolver.resolveToJson(coordinate);

        assertNotNull(payload);
        JsonNode result = OBJECT_MAPPER.readTree(payload);
        assertTrue(result.isObject(), "Result should be a JSON object");
        assertEquals(coordinate, result.path("semantics").path("coordinate").asText());
        assertEquals("aether", result.path("semantics").path("source").asText());
        assertTrue(result.path("root").isObject(), "root should be an object");
        assertTrue(result.path("nodes").isArray(), "nodes should be an array");
        assertTrue(result.path("edges").isArray(), "edges should be an array");
        assertTrue(result.path("nodes").size() >= 1, "at least the root node should be present");
        assertTrue(result.path("metrics").path("node_count").asInt() >= 1, "metrics should include node_count");
    }

    @ParameterizedTest
    @DisplayName("Reject invalid Maven coordinates")
    @ValueSource(strings = {
            "",
            "invalid:format",
            "group:artifact:"
    })
    public void testResolveToJsonInvalidCoordinate(String coordinate) {
        Exception exception = assertThrows(Exception.class, () -> MavenSingleResolver.resolveToJson(coordinate));
        assertNotNull(exception.getMessage());
    }
}
