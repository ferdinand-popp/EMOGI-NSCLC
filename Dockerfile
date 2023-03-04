# hash:sha256:809a08d4b6d2ee45a639c8c31040ae8d86d85e282efb0146866a15940990ca5e
FROM registry.codeocean.com/codeocean/miniconda3:4.5.11-python3.7-cuda9.2-cudnn7-ubuntu18.04

ARG DEBIAN_FRONTEND=noninteractive

RUN conda install -y \
        jupyter==1.0.0 \
        jupyterlab==2.1.5 \
        seaborn==0.10.1 \
        tensorflow==1.15.0 \
    && conda clean -ya

RUN pip install -U --no-cache-dir \
    pip==20.2.2
RUN pip install -U --no-cache-dir \
    goatools==1.0.6 \
    h5py==2.10.0 \
    matplotlib==3.1.2 \
    matplotlib-venn==0.11.5 \
    mygene==3.1.0 \
    networkx==2.2 \
    numpy==1.19.1 \
    scikit-learn==0.23.2 \
    scipy==1.4.1 \
    tensorflow==1.15.0 \
    upsetplot==0.4.0 \
    -e git+https://github.com/marcoancona/DeepExplain.git@87fb43a13ac2a3b285a030b87df899cc40100c94#egg=deepexplain \
    -e git+https://github.com/tkipf/gcn.git@39a4089fe72ad9f055ed6fdb9746abdcfebc4d81#egg=gcn

COPY postInstall /
# RUN /postInstall
