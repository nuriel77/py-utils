pipeline {
  agent any
  parameters {
    string(name: 'payload', defaultValue: '{}', description: 'JSON payload')
  }
  stages {
    stage('start') {
      steps {
        sh 'echo "${params.payload}"'
      }
    }
  }
}
