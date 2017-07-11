pipeline {
  agent any
  options([[$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false], parameters([string(defaultValue: '{}', description: 'payload', name: 'payload')]), pipelineTriggers([])])
  stages {
    stage('start') {
      steps {
        sh 'env'
      }
    }
  }
}
