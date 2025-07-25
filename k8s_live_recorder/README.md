# Undo LiveRecorder Kubernetes Sidecar Demo

This is a demo of Undo's [LiveRecorder](https://docs.undo.io/UsingTheLiveRecorderTool.html) recording an application in a Kubernetes pod.
LiveRecorder is hosted in a sidecar container that runs alongside the main application container in the same pod.
A wrapper application monitors for specific annotations, and starts the recording of the main application process when instructed. 
As LiveRecorder is hosted in a sidecar container no changes are needed to be made to the existing main application container.
When recording has stopped, the resultant *.undo file is then uploaded to an S3 bucket.

Minikube is used for demonstration purposes.

## Requirements

- [Minikube](https://minikube.sigs.k8s.io/docs/)
- AWS credentials for S3 upload
- `live-record` binary and `undolr/` folder from an Undo release. Obtain a [free trail here](https://undo.io/udb-free-trial/).


## Setup

1. Copy `live-record` binary and `undolr/` folder to `sidecar/` dir.
1. `minikube start`
1. `alias kubectl="minikube kubectl --"` (for convenience)
1. Use minikube image registry `eval $(minikube docker-env)`
1. `docker buildx build -t undo/broken-go-app:latest -f app/Dockerfile app --load`
1. `docker buildx build -t undo/undo-lr-sidecar:latest -f sidecar/Dockerfile sidecar --load`
1. Create the required secrets for AWS credentials:
   ```
   kubectl create secret generic s3 \
     --from-literal=AWS_ACCESS_KEY_ID=your-access-key \
     --from-literal=AWS_SECRET_ACCESS_KEY=your-secret-key \
     --from-literal=S3_BUCKET_NAME=your-bucket \
     --from-literal=S3_REGION=your-region
   ```
1. `kubectl apply -f k8s/recorder-role.yaml`
1. `kubectl apply -f k8s/recorder-rolebinding.yaml`
1. `kubectl apply -f k8s/deployment.yaml`
1. `kubectl apply -f k8s/service.yaml`
1. (To restart deployment and redeploy containers `kubectl rollout restart deployment/broken-go-app-deployment`)

## Test Demo

This very simple demo will show you how to record an application that crashes, get the recording from S3 and then replay using Undo's extended version of [Delve](https://docs.undo.io/GoDelve.html).

1. Check containers and programs are running:
```
  kubectl get pods -l app=broken-go-app -o wide
  kubectl describe pod $(kubectl get pods --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
  kubectl logs $(kubectl get pods --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}') -c undo-lr-sidecar
  kubectl logs $(kubectl get pods --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}') -c broken-go-app
```
1. Start recording `kubectl annotate pod $(kubectl get pods --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}') undo.io/live-record=start --overwrite || true`
1. Get service url `minikube service broken-go-app-service --url` - NOTE: if using docker driver, you will need to perform the curl request in a new terminal while this command continues to run.
1. Make the target application crash `curl -s "<service-url>/crash"`
1. Stop recording `kubectl annotate pod $(kubectl get pods --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}') undo.io/live-record=stop --overwrite || true` - NOTE: recording will stop due to the crash

1. List uploaded recordings `aws s3 ls s3://S3-BUCKET-NAME/recordings/`
1. Copy recording to local machine `aws s3 cp s3://S3-BUCKET-NAME/recordings/RECORDING-FILE-NAME.undo .`
1. Use Delve to replay recording `dlv replay RECORDING-FILE-NAME.undo`