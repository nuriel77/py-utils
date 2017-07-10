pipeline {
  agent any
  stages {
    stage('start') {
      steps {
        sh 'echo "${params.payload}"'
      }
    }
  }
  parameters {
    string(name: 'payload', defaultValue: '{}', description: 'JSON payload')
  }
}