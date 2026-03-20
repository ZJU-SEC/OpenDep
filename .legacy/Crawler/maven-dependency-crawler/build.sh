#!/bin/bash
WORKING_DIR=`pwd`

BUILD_DIR=${WORKING_DIR}/build

JAR=${WORKING_DIR}/target/MavenEcoSystem-1.0.0-jar-with-dependencies.jar

mvn flyway:migrate
mvn clean package

rm -f ${BUILD_DIR}/MavenEcoSystem.jar
mv -f ${JAR} ${BUILD_DIR}/MavenEcoSystem.jar

mvn clean