#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: https://github.com/monero-project/mininero
# Author: Dusan Klinec, ph4r05, 2018
# see https://eprint.iacr.org/2015/1098.pdf

import logging
from . import crypto

logger = logging.getLogger(__name__)


def keyVector(rows):
    """
    Empty key vector
    :param rows:
    :return:
    """
    return [None] * rows


def keyMatrix(rows, cols):
    """
    first index is columns (so slightly backward from math)
    :param rows:
    :param cols:
    :return:
    """
    rv = [None] * cols
    for i in range(0, cols):
        rv[i] = keyVector(rows)
    return rv


def hashKeyVector(v):
    """
    Hashes key vector
    :param v:
    :return:
    """
    return [crypto.hash_to_ec(vi) for vi in v]


def vScalarMultBase(v):
    """
    Creates vector of points from scalars
    :param v:
    :return:
    """
    return [crypto.scalarmult_base(a) for a in v]


def keyImageV(x):
    """
    Takes as input a keyvector, returns the keyimage-vector
    :param x:
    :return:
    """
    return [crypto.scalarmult(crypto.hash_to_ec(crypto.scalarmult_base(xx)), xx) for xx in x]


def skvGen(n):
    """
    Generates vector of scalars
    :param n:
    :return:
    """
    return [crypto.random_scalar() for i in range(0, n)]


def skmGen(r, c):
    """
    Generates matrix of scalars
    :param r:
    :param c:
    :return:
    """
    rv = keyMatrix(r, c)
    for i in range(0, c):
        rv[i] = skvGen(r)
    return rv


def add_keys1(a, b, B):
    """
    aG + bB, G is basepoint
    :param a:
    :param b:
    :param B:
    :return:
    """
    return crypto.point_add(crypto.scalarmult_base(a), crypto.scalarmult(B, b))


def add_keys2(a, A, b, B):
    """
    aA + bB
    :param a:
    :param A:
    :param b:
    :param B:
    :return:
    """
    return crypto.point_add(crypto.scalarmult(A, a), crypto.scalarmult(B, b))


def MLSAG_Gen(pk, xx, index):
    rows = len(xx)
    cols = len(pk)
    logger.debug("Generating MG sig of size %s x %s" % (rows, cols))
    logger.debug("index is: %s, %s" % (index, pk[index]))
    c = [None] * cols
    alpha = skvGen(rows)
    I = keyImageV(xx)
    L = keyMatrix(rows, cols)
    R = keyMatrix(rows, cols)
    s = keyMatrix(rows, cols)

    m = ''.join(pk[0])
    for i in range(1, cols):
        m = m + ''.join(pk[i])

    L[index] = [crypto.scalarmult_base(aa) for aa in alpha]  # L = aG
    Hi = hashKeyVector(pk[index])
    R[index] = [crypto.scalarmult(Hi[ii], alpha[ii]) for ii in range(0, rows)]  # R = aI
    oldi = index
    i = (index + 1) % cols
    c[i] = crypto.cn_fast_hash(m+''.join(L[oldi]) + ''.join(R[oldi]))
    
    while i != index:
        s[i] = skvGen(rows)
        L[i] = [add_keys1(s[i][j], c[i], pk[i][j]) for j in range(0, rows)]

        Hi = hashKeyVector(pk[i])
        R[i] = [add_keys2( s[i][j], Hi[j], c[i], I[j]) for j in range(0, rows)]
        oldi = i
        i = (i + 1) % cols
        c[i] = crypto.cn_fast_hash(m+''.join(L[oldi]) + ''.join(R[oldi]))

    s[index] = [crypto.sc_mulsub(alpha[j], c[index], xx[j]) for j in range(0, rows)]  # alpha - c * x
    return I, c[0], s


def MLSAG_Ver(pk, I, c0, s ):
    rows = len(pk[0])
    cols = len(pk)
    logger.debug("verifying MG sig of dimensions %s x %s" % (rows, cols))
    c = [None] * (cols + 1)
    c[0] = c0
    L = keyMatrix(rows, cols)
    R = keyMatrix(rows, cols)
    m = ''.join(pk[0])
    for i in range(1, cols):
        m = m + ''.join(pk[i])
    i = 0
    while i < cols:
        L[i] = [add_keys1(s[i][j], c[i], pk[i][j]) for j in range(0, rows)]

        Hi = hashKeyVector(pk[i])
        R[i] = [add_keys2( s[i][j], Hi[j], c[i], I[j]) for j in range(0, rows)]

        oldi = i
        i = i + 1
        c[i] = crypto.cn_fast_hash(m+''.join(L[oldi]) + ''.join(R[oldi]))

    return c0 == c[cols]
