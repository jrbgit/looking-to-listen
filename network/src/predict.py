import os
import glob
import argparse

import chainer
from chainer import cuda

import env
import common.util as util
import modules.operation as op
from network.audio_only_net import Audio_Only_Net
from network.double_complex_net import Double_Complex_Net
from network.single_complex_net import Single_Complex_Net


xp = env.xp


def get_data():

    audio = sorted(glob.glob(os.environ["DATASET_DIR"] + "/movie/audio/*"))
    noise = xp.stack([xp.load(i).T for i in audio]).astype(xp.float32)

    visual = sorted(glob.glob(os.environ["DATASET_DIR"] + "/movie/visual/*"))
    face1 = xp.stack([xp.load(i).T for i in visual]).astype(xp.float32)
    face1 = face1[:, :, :, xp.newaxis]

    visual = ["/data/dataset/avspeech/visual/hoge_0.npy", "/data/dataset/avspeech/visual/hoge_0.npy", "/data/dataset/avspeech/visual/hoge_0.npy"]
    face2 = xp.stack([xp.load(i).T for i in visual]).astype(xp.float32)
    face2 = face2[:, :, :, xp.newaxis]

    return noise, face1, face2


def predict(model):

    noise, face1, face2 = get_data()
    compressed_noise, _ = op.compress_audio(noise)

    print("estimate mask...")
    mask1, mask2 = model.estimate_mask(spec=compressed_noise, face1=face1, face2=face2)
    # mask1, mask2 = model.estimate_mask(spec=compressed_noise, face=face1)

    print("mul mask...")
    compressed_separated1 = op.mul(mask1, compressed_noise).data
    compressed_separated2 = op.mul(mask2, compressed_noise).data
    if env.gpu:
        compressed_noise = chainer.cuda.to_cpu(compressed_noise)
        compressed_separated1 = chainer.cuda.to_cpu(compressed_separated1)
        compressed_separated2 = chainer.cuda.to_cpu(compressed_separated2)

    print("reconstruct audio...")
    n = op.reconstruct_audio_complex(compressed_noise)
    y1 = op.reconstruct_audio_complex(compressed_separated1)
    y2 = op.reconstruct_audio_complex(compressed_separated2)

    print("save files...")
    for i in range(n.shape[2]):
        print("{0}/{1}".format(i + 1, n.shape[2]))
        util.istft_and_save("{}/{}-synthesis.wav".format(os.environ['RESULT_DIR'], i), n[:, :, i])
        util.istft_and_save("{}/{}-separated1.wav".format(os.environ['RESULT_DIR'], i), y1[:, :, i])
        util.istft_and_save("{}/{}-separated2.wav".format(os.environ['RESULT_DIR'], i), y2[:, :, i])


def main(args):

    if not os.path.exists(os.environ['RESULT_DIR']):
        os.makedirs(os.environ['RESULT_DIR'])

    if env.gpu:
        cuda.get_device(args.gpu).use()

    print("loading model...")
    if env.INPUT_FACE == 1:
        model = Single_Complex_Net()
    elif env.INPUT_FACE == 2:
        model = Double_Complex_Net()
    else:
        model = Audio_Only_Net()

    if args.resume.find("snapshot") > -1:
        chainer.serializers.load_npz(args.resume, model, path="updater/model:main/")
    else:
        model_name = os.environ["MODEL_DIR"] + "/" + env.MODEL_NAME + "_model.npz"
        chainer.serializers.load_npz(model_name, model)

    if env.gpu:
        model.to_gpu(args.gpu)
    elif args.ideep:
        model.to_intel64()

    with chainer.using_config("train", False), \
            chainer.using_config('enable_backprop', False), \
            chainer.using_config('type_check', False), \
            chainer.using_config('use_ideep', 'always' if args.ideep else 'never'):
        predict(model)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='predict'
    )
    parser.add_argument("--resume", default="", help="use snapshot")
    parser.add_argument("--ideep", action='store_true', help="ideep (CPU Only)")
    parser.add_argument("--gpu", "-g", type=int, default=0, help="specify GPU")
    args = parser.parse_args()

    main(args)
