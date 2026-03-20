package cn.edu.zju.nirvana;


import cn.edu.zju.nirvana.core.pomCrawler.PomCrawler;
import cn.edu.zju.nirvana.core.pomIndexer.CentralIndexer;
import cn.edu.zju.nirvana.core.resolver.DepTree;
import cn.edu.zju.nirvana.core.resolver.GetDependencyHierarchy;
import cn.edu.zju.nirvana.core.resolver.GetDirectDependencies;
import org.apache.commons.cli.*;
// import org.apache.log4j.Logger;
import org.codehaus.plexus.PlexusContainerException;
import org.codehaus.plexus.component.repository.exception.ComponentLookupException;

import java.io.IOException;

public class MavenEcoSystem
{
    private static final Options options = new Options();

    // private static final Logger LOGGER = Logger.getLogger(MavenEcoSystem.class);


    private static void help()
    {
        HelpFormatter helpFormatter = new HelpFormatter();
        helpFormatter.printHelp("MavenEcoSystem", options);
        System.exit(0);
    }

    public static void main(String[] args) throws PlexusContainerException, ComponentLookupException, IOException {
        options.addOption( "i", "indexer", false, "Synchronize index information" );
        options.addOption( "c", "crawl", false, "Crawl the component's POM file" );
        options.addOption( "d", "deptree", false, "Generate dependency tree" );
        options.addOption( "h", "help", false, "View command description" );
        CommandLineParser parser = new DefaultParser();

        try {
            CommandLine cmd = parser.parse( options, args );

            if (cmd.hasOption("h"))
            {
                help();
            } else if (cmd.hasOption("i"))
            {
                // LOGGER.info( "Synchronize index information" );
                CentralIndexer centralIndexer = new CentralIndexer();
                centralIndexer.Sync();
            } else if (cmd.hasOption("c"))
            {
                // LOGGER.info( "Crawl the component's POM file" );
                PomCrawler.crawling();
            } else if (cmd.hasOption("d"))
            {
                // LOGGER.info( "Generate dependency tree" );
                DepTree.Run();
            } else
            {
                help();
            }
        } catch (ParseException e)
        {
            e.printStackTrace();
        }


        // LOGGER.info("DONE");
    }
}
