pipeline {
  agent any
  parameters {
    string(defaultValue: '{}', description: 'payload', name: 'payload')
  }
  stages {
    stage('start') {
      steps {
        sh 'env'
      }
    }
  }
}
