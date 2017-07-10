pipeline {
  agent any
  stages {
    stage('start') {
      steps {
        sh 'env'
      }
    }
  }
  parameters {
    string(name: 'payload', defaultValue: '{}', description: 'JSON payload')
  }
}
