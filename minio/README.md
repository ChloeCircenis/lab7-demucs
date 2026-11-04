# Min.io README
Because MinIO is no longer supported, this project uses RustFS alongside MinIO. RustFS is deployed as a Kuberneted container but maintains the existing MinIO Python interface that was shown in the Kubernetes tutorial. Because RustFS is an S3-compatible interface, I was able to switch storage systems without modifying application logic. 

Everything is still labeled as MinIO, but the underlying storage system is RustFS. 
