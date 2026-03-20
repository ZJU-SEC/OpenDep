package cn.edu.zju.nirvana.core.resolver.pomBuilder;

import org.apache.maven.model.building.DefaultModelBuilder;
import org.apache.maven.model.building.ModelProblemCollectorExt;

public class EffectiveModelBuilder extends DefaultModelBuilder
{
    protected boolean hasModelErrors(ModelProblemCollectorExt problems)
    {
        return false;
    }
}