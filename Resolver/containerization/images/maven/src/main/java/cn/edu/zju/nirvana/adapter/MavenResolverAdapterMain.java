package cn.edu.zju.nirvana.adapter;

public class MavenResolverAdapterMain {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: MavenResolverAdapterMain <groupId:artifactId:version>");
            System.exit(1);
            return;
        }

        String coordinate = args[0];
        String payload = MavenSingleResolver.resolveToJson(coordinate);
        System.out.println(payload);
    }
}
