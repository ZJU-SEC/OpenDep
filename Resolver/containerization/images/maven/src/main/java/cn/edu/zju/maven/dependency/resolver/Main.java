package cn.edu.zju.maven.dependency.resolver;

import cn.edu.zju.maven.dependency.resolver.core.SimpleDependencyResolver;
import java.util.Arrays;
import java.util.List;

/**
 * Main entry point for Maven Dependency Tree Generator
 * Provides user-friendly command line parameter handling for dependency tree generation.
 */
public class Main {
    
    private static final String PROGRAM_NAME = "Maven Dependency Tree Generator";
    private static final String VERSION = "1.0.0";
    
    public static void main(String[] args) {
        try {
            if (args.length == 0) {
                printUsage();
                return;
            }
            
            // Parse command line arguments
            CommandLineArgs parsedArgs = parseArguments(args);
            
            if (parsedArgs.showHelp) {
                printUsage();
                return;
            }
            
            if (parsedArgs.showVersion) {
                printVersion();
                return;
            }
            
            // Validate Maven coordinate
            if (parsedArgs.coordinate == null || parsedArgs.coordinate.trim().isEmpty()) {
                System.err.println("Error: Maven coordinate is required.");
                printUsage();
                System.exit(1);
            }
            
            // Set timeout if specified
            if (parsedArgs.timeoutSeconds > 0) {
                SimpleDependencyResolver.setTimeout(parsedArgs.timeoutSeconds);
            }
            
            // Generate dependency tree
            handleGenerateCommand(parsedArgs.coordinate, parsedArgs.outputFile);
            
        } catch (IllegalArgumentException e) {
            System.err.println("Error: " + e.getMessage());
            printUsage();
            System.exit(1);
        } catch (Exception e) {
            System.err.println("Error generating dependency tree: " + e.getMessage());
            if (isVerbose(args)) {
                e.printStackTrace();
            }
            System.exit(1);
        }
    }
    
    /**
     * Parse command line arguments into a structured format
     */
    private static CommandLineArgs parseArguments(String[] args) {
        CommandLineArgs result = new CommandLineArgs();
        List<String> argList = Arrays.asList(args);
        
        for (int i = 0; i < args.length; i++) {
            String arg = args[i];
            
            switch (arg) {
                case "-h":
                case "--help":
                    result.showHelp = true;
                    return result;
                    
                case "-v":
                case "--version":
                    result.showVersion = true;
                    return result;
                    
                case "-o":
                case "--output":
                    if (i + 1 >= args.length) {
                        throw new IllegalArgumentException("Output file option requires a filename");
                    }
                    result.outputFile = args[++i];
                    break;
                    
                case "-t":
                case "--timeout":
                    if (i + 1 >= args.length) {
                        throw new IllegalArgumentException("Timeout option requires a value in seconds");
                    }
                    try {
                        result.timeoutSeconds = Long.parseLong(args[++i]);
                        if (result.timeoutSeconds <= 0) {
                            throw new IllegalArgumentException("Timeout must be a positive number");
                        }
                    } catch (NumberFormatException e) {
                        throw new IllegalArgumentException("Invalid timeout value: " + args[i]);
                    }
                    break;
                    
                case "--verbose":
                    result.verbose = true;
                    break;
                    
                default:
                    // If it doesn't start with -, assume it's the Maven coordinate
                    if (!arg.startsWith("-")) {
                        if (result.coordinate == null) {
                            result.coordinate = arg;
                        } else {
                            throw new IllegalArgumentException("Multiple Maven coordinates specified: " + result.coordinate + " and " + arg);
                        }
                    } else {
                        throw new IllegalArgumentException("Unknown option: " + arg);
                    }
                    break;
            }
        }
        
        return result;
    }
    
    /**
     * Handle the dependency tree generation command
     */
    private static void handleGenerateCommand(String coordinate, String outputFile) throws Exception {
        // Validate Maven coordinate format
        if (!isValidMavenCoordinate(coordinate)) {
            throw new IllegalArgumentException("Invalid Maven coordinate format. Expected: groupId:artifactId:version");
        }
        
        System.out.println("Generating dependency tree for: " + coordinate);
        
        // Generate and output the dependency tree
        if (outputFile != null && !outputFile.trim().isEmpty()) {
            SimpleDependencyResolver.resolveDependencyTreeAndSave(coordinate, outputFile);
            System.out.println("Dependency tree saved to: " + outputFile);
        } else {
            SimpleDependencyResolver.resolveDependencyTreeAndPrint(coordinate);
        }
    }
    
    /**
     * Validate Maven coordinate format (groupId:artifactId:version)
     */
    private static boolean isValidMavenCoordinate(String coordinate) {
        if (coordinate == null || coordinate.trim().isEmpty()) {
            return false;
        }
        
        String[] parts = coordinate.split(":");
        if (parts.length != 3) {
            return false;
        }
        
        // Check that each part is not empty
        for (String part : parts) {
            if (part.trim().isEmpty()) {
                return false;
            }
        }
        
        return true;
    }
    
    /**
     * Check if verbose mode is enabled
     */
    private static boolean isVerbose(String[] args) {
        return Arrays.asList(args).contains("--verbose");
    }
    
    /**
     * Print program usage information
     */
    private static void printUsage() {
        System.out.println(PROGRAM_NAME + " v" + VERSION);
        System.out.println();
        System.out.println("DESCRIPTION:");
        System.out.println("    Generate dependency tree for Maven artifacts in JSON format");
        System.out.println();
        System.out.println("USAGE:");
        System.out.println("    java -jar maven-dependency-tree-generator.jar [OPTIONS] <groupId:artifactId:version>");
        System.out.println();
        System.out.println("ARGUMENTS:");
        System.out.println("    <groupId:artifactId:version>    Maven coordinate of the artifact to analyze");
        System.out.println();
        System.out.println("OPTIONS:");
        System.out.println("    -h, --help                      Show this help message and exit");
        System.out.println("    -v, --version                   Show version information and exit");
        System.out.println("    -o, --output <file>             Save output to specified file instead of console");
        System.out.println("    -t, --timeout <seconds>         Set timeout for dependency resolution (default: 180)");
        System.out.println("    --verbose                       Enable verbose error output");
        System.out.println();
        System.out.println("EXAMPLES:");
        System.out.println("    # Generate dependency tree and print to console");
        System.out.println("    java -jar maven-dependency-tree-generator.jar org.springframework:spring-core:5.3.21");
        System.out.println();
        System.out.println("    # Save dependency tree to file");
        System.out.println("    java -jar maven-dependency-tree-generator.jar junit:junit:4.13.2 -o dependencies.json");
        System.out.println();
        System.out.println("    # Set custom timeout");
        System.out.println("    java -jar maven-dependency-tree-generator.jar -t 60 org.springframework:spring-core:5.3.21");
        System.out.println();
        System.out.println("    # Combine options");
        System.out.println("    java -jar maven-dependency-tree-generator.jar -t 120 -o output.json org.apache.commons:commons-lang3:3.12.0");
        System.out.println();
        System.out.println("COORDINATE FORMAT:");
        System.out.println("    The Maven coordinate must be in the format: groupId:artifactId:version");
        System.out.println("    Example: org.springframework:spring-core:5.3.21");
    }
    
    /**
     * Print version information
     */
    private static void printVersion() {
        System.out.println(PROGRAM_NAME + " version " + VERSION);
        System.out.println("A lightweight tool for generating Maven dependency trees in JSON format.");
    }
    
    /**
     * Internal class to hold parsed command line arguments
     */
    private static class CommandLineArgs {
        String coordinate;
        String outputFile;
        long timeoutSeconds = -1;
        boolean showHelp = false;
        boolean showVersion = false;
        boolean verbose = false;
    }
} 