package cn.edu.zju.nirvana.core.resolver.util;

public class PomUtils
{
    public static String DefaultPom(String g, String a, String v)
    {
        return String.format(
                "<project> " +
                        "<modelVersion>4.0.0</modelVersion> " +
                        "<groupId>%s</groupId>" +
                        "<artifactId>%s</artifactId>" +
                        "<version>%s</version>" +
                        "</project>",
                g, a, v
        );
    }
}