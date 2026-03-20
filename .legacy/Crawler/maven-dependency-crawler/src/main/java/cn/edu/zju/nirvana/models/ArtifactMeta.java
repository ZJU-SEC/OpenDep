package cn.edu.zju.nirvana.models;

import org.apache.commons.codec.digest.DigestUtils;
import org.apache.maven.index.ArtifactInfo;

import java.sql.Timestamp;
import java.util.Objects;

public class ArtifactMeta
{
    private String md5;

    private String g;

    private String a;

    private String v;

    private String describe;

    private Timestamp ts;

    private Boolean rvd;

    private String depTree;

    private Boolean disk;

    private String pom;


    public ArtifactMeta()
    {
    }

    public ArtifactMeta(ArtifactInfo artifactInfo)
    {
        this.md5 = DigestUtils.md5Hex(artifactInfo.getGroupId() + ":" + artifactInfo.getArtifactId() + ":" + artifactInfo.getVersion()).toUpperCase();
        this.g = artifactInfo.getGroupId();
        this.a = artifactInfo.getArtifactId();
        this.v = artifactInfo.getVersion();
        this.describe = artifactInfo.getDescription();
        this.ts = new Timestamp(artifactInfo.getLastModified());
        this.rvd = false;
    }

    @Override
    public String toString()
    {
        return "ArtifactMeta{" +
                "md5='" + md5 + '\'' +
                ", g='" + g + '\'' +
                ", a='" + a + '\'' +
                ", v='" + v + '\'' +
                '}';
    }

    @Override
    public boolean equals(Object that)
    {
        if (this == that) return true;

        if (that == null || this.getClass() != that.getClass())
            return false;

        return Objects.equals(this.md5, ((ArtifactMeta) that).md5);
    }

    @Override
    public int hashCode()
    {
        return (this.g + ":" + this.a + ":" + this.v).hashCode();
    }

    public String getMd5()
    {
        return md5;
    }

    public void setMd5(String md5)
    {
        this.md5 = md5;
    }

    public String getG()
    {
        return g;
    }

    public void setG(String g)
    {
        this.g = g;
    }

    public String getA()
    {
        return a;
    }

    public void setA(String a)
    {
        this.a = a;
    }

    public String getV()
    {
        return v;
    }

    public void setV(String v)
    {
        this.v = v;
    }

    public String getDescribe()
    {
        return describe;
    }

    public void setDescribe(String describe)
    {
        this.describe = describe;
    }

    public Timestamp getTs()
    {
        return ts;
    }

    public void setTs(Timestamp ts)
    {
        this.ts = ts;
    }

    public Boolean getRvd() {
        return rvd;
    }

    public void setRvd(Boolean rvd) {
        this.rvd = rvd;
    }

    public Boolean getDisk() {
        return disk;
    }

    public void setDisk(Boolean disk) {
        this.disk = disk;
    }

    public String getDepTree() {
        return depTree;
    }

    public void setDepTree(String depTree) {
        this.depTree = depTree;
    }

    public String getPom() {
        return pom;
    }

    public void setPom(String pom) {
        this.pom = pom;
    }
}
