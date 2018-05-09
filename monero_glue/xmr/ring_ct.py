#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: https://github.com/monero-project/mininero
# Author: Dusan Klinec, ph4r05, 2018

import logging

from monero_serialize import xmrtypes
from monero_glue.xmr import mlsag2, crypto, common, asnl, monero

logger = logging.getLogger(__name__)
ATOMS = 64

    
def d2b(n, digits):
    b = [0] * digits
    i = 0
    while n:
        b[i] = n & 1
        i = i + 1
        n >>= 1
    return b 


def sum_Ci(Cis):
    """
    Sums points
    :param Cis:
    :return:
    """
    CSum = crypto.identity()
    for i in Cis:
        CSum = crypto.point_add(CSum, i)
    return CSum


def prove_range(amount, last_mask=None, use_asnl=False, mem_opt=True):
    """
    Range proof generator.
    :param amount:
    :param last_mask:
    :param use_asnl:
    :param mem_opt: memory optimized
    :return:
    """
    if use_asnl and mem_opt:
        raise ValueError('ASNL not in memory optimized variant')

    if use_asnl and not mem_opt:
        return prove_range_orig(amount, last_mask=last_mask, use_asnl=True)
    else:
        return prove_range_mem(amount, last_mask=last_mask)


def prove_range_orig(amount, last_mask=None, use_asnl=False):
    """
    Gives C, and mask such that \sumCi = C
    c.f. http:#eprint.iacr.org/2015/1098 section 5.1

    Ci is a commitment to either 0 or 2^i, i=0,...,63
    thus this proves that "amount" is in [0, 2^ATOMS]
    mask is a such that C = aG + bH, and b = amount
    :param amount:
    :param last_mask: ai[ATOMS-1] will be computed as \sum_{i=0}^{ATOMS-2} a_i - last_mask
    :param use_asnl: use ASNL, used before Borromean
    :return: sumCi, mask, RangeSig.
        sumCi is Pedersen commitment on the amount value. sumCi = aG + amount*H
        mask is "a" from the Pedersent commitment above.
    """
    bb = d2b(amount, ATOMS)  # gives binary form of bb in "digits" binary digits
    logger.info("amount, amount in binary %s %s" % (amount, bb))
    ai = [None] * len(bb)
    Ci = [None] * len(bb)
    CiH = [None] * len(bb)  # this is like Ci - 2^i H
    H2 = crypto.gen_Hpow(ATOMS)
    a = 0
    for i in range(0, ATOMS):
        ai[i] = crypto.random_scalar()
        if last_mask is not None and i == ATOMS - 1:
            ai[i] = crypto.sc_sub(last_mask, a)

        a = crypto.sc_add(a, ai[i])  # creating the total mask since you have to pass this to receiver...
        if bb[i] == 0:
            Ci[i] = crypto.scalarmult_base(ai[i])
        if bb[i] == 1:
            Ci[i] = crypto.point_add(crypto.scalarmult_base(ai[i]), H2[i])
        CiH[i] = crypto.point_sub(Ci[i], H2[i])

    A = xmrtypes.BoroSig()

    if use_asnl:
        A.s0, A.s1, A.ee = asnl.gen_asnl(ai, Ci, CiH, bb)
    else:
        A.s0, A.s1, A.ee = mlsag2.gen_borromean(ai, Ci, CiH, bb)
    
    R = xmrtypes.RangeSig()
    R.asig = A
    R.Ci = Ci

    C = sum_Ci(Ci)
    return C, a, R


def prove_range_mem(amount, last_mask=None):
    """
    Memory optimized range proof.
    Gives C, and mask such that \sumCi = C
    c.f. http:#eprint.iacr.org/2015/1098 section 5.1

    Ci is a commitment to either 0 or 2^i, i=0,...,63
    thus this proves that "amount" is in [0, 2^ATOMS]
    mask is a such that C = aG + bH, and b = amount
    :param amount:
    :param last_mask: ai[ATOMS-1] will be computed as \sum_{i=0}^{ATOMS-2} a_i - last_mask
    :param use_asnl: use ASNL, used before Borromean
    :return: sumCi, mask, RangeSig.
        sumCi is Pedersen commitment on the amount value. sumCi = aG + amount*H
        mask is "a" from the Pedersent commitment above.
    """
    n = ATOMS
    bb = d2b(amount, n)  # gives binary form of bb in "digits" binary digits
    ai = [None] * len(bb)
    Ci = [None] * len(bb)
    a = 0

    C = crypto.identity()
    alpha = mlsag2.key_zero_vector(n)
    s1 = mlsag2.key_zero_vector(n)
    c_H = crypto.gen_H()
    kck = common.get_keccak()  # ee computation

    # First pass, generates: ai, alpha, Ci, ee, s1
    for ii in range(n):
        ai[ii] = crypto.random_scalar()
        if last_mask is not None and ii == ATOMS - 1:
            ai[ii] = crypto.sc_sub(last_mask, a)

        a = crypto.sc_add(a, ai[ii])  # creating the total mask since you have to pass this to receiver...

        alpha[ii] = crypto.random_scalar()
        L = crypto.scalarmult_base(alpha[ii])

        if bb[ii] == 0:
            Ci[ii] = crypto.scalarmult_base(ai[ii])
        else:
            Ci[ii] = crypto.point_add(crypto.scalarmult_base(ai[ii]), c_H)
        C = crypto.point_add(C, Ci[ii])

        if bb[ii] == 0:
            s1[ii] = crypto.random_scalar()
            c = crypto.hash_to_scalar(crypto.encodepoint(L))
            L = mlsag2.add_keys1(s1[ii], c, crypto.point_sub(Ci[ii], c_H))
            kck.update(crypto.encodepoint(L))

        else:
            kck.update(crypto.encodepoint(L))

        c_H = crypto.scalarmult(c_H, 2)

    # Compute ee, memory cleanup
    ee = crypto.sc_reduce32(crypto.decodeint(kck.digest()))
    del kck

    # Second phase computes: s0, s1
    c_H = crypto.gen_H()
    s0 = mlsag2.key_zero_vector(n)

    for jj in range(n):
        if not bb[jj]:
            s0[jj] = crypto.sc_mulsub(alpha[jj], ai[jj], ee)

        else:
            s0[jj] = crypto.random_scalar()
            LL = mlsag2.add_keys1(s0[jj], ee, Ci[jj])
            cc = crypto.hash_to_scalar(crypto.encodepoint(LL))
            s1[jj] = crypto.sc_mulsub(alpha[jj], ai[jj], cc)
        c_H = crypto.scalarmult(c_H, 2)

    A = xmrtypes.BoroSig()
    A.s0, A.s1, A.ee = s0, s1, ee

    R = xmrtypes.RangeSig()
    R.asig = A
    R.Ci = Ci

    return C, a, R


def ver_range(Ci, ags, use_asnl=False):
    """
    Verifies that \sum Ci = C and that each Ci is a commitment to 0 or 2^i
    :param Ci:
    :param ags:
    :param use_asnl: use ASNL, used before Borromean
    :return:
    """
    n = ATOMS
    CiH = [None] * n
    C_tmp = crypto.identity()
    H2 = crypto.gen_Hpow(ATOMS)
    for i in range(0, n):
        CiH[i] = crypto.point_sub(ags.Ci[i], H2[i])
        C_tmp = crypto.point_add(C_tmp, ags.Ci[i])

    if not crypto.point_eq(C_tmp, Ci):
        return 0

    if use_asnl:
        return asnl.ver_asnl(ags.Ci, CiH, ags.asig.s0, ags.asig.s1, ags.asig.ee)
    else:
        return mlsag2.ver_borromean(ags.Ci, CiH, ags.asig.s0, ags.asig.s1, ags.asig.ee)


# Ring-ct MG sigs
# Prove:
#   c.f. http:#eprint.iacr.org/2015/1098 section 4. definition 10. 
#   This does the MG sig on the "dest" part of the given key matrix, and 
#   the last row is the sum of input commitments from that column - sum output commitments
#   this shows that sum inputs = sum outputs
# Ver:
#   verifies the above sig is created corretly


def ecdh_encode(unmasked, receiver_pk=None, derivation=None):
    """
    Elliptic Curve Diffie-Helman: encodes and decodes the amount b and mask a
    where C= aG + bH
    :param unmasked:
    :param receiver_pk:
    :param derivation:
    :return:
    """
    rv = xmrtypes.EcdhTuple()
    if derivation is None:
        esk = crypto.random_scalar()
        rv.senderPk = crypto.scalarmult_base(esk)
        derivation = crypto.encodepoint(crypto.scalarmult(receiver_pk, esk))

    sharedSec1 = crypto.hash_to_scalar(derivation)
    sharedSec2 = crypto.hash_to_scalar(crypto.encodeint(sharedSec1))

    rv.mask = crypto.sc_add(unmasked.mask, sharedSec1)
    rv.amount = crypto.sc_add(unmasked.amount, sharedSec2)
    return rv

    
def ecdh_decode(masked, receiver_sk=None, derivation=None):
    """
    Elliptic Curve Diffie-Helman: encodes and decodes the amount b and mask a
    where C= aG + bH
    :param masked:
    :param receiver_sk:
    :param derivation:
    :return:
    """
    rv = xmrtypes.EcdhTuple()

    if derivation is None:
        derivation = crypto.scalarmult(masked.senderPk, receiver_sk)

    sharedSec1 = crypto.hash_to_scalar(derivation)
    sharedSec2 = crypto.hash_to_scalar(crypto.encodeint(sharedSec1))

    rv.mask = crypto.sc_sub(masked.mask, sharedSec1)
    rv.amount = crypto.sc_sub(masked.amount, sharedSec2)
    return rv


#
# RingCT protocol
#


def decode_rct(rv, sk, i):
    """
    c.f. http:#eprint.iacr.org/2015/1098 section 5.1.1
    Uses the attached ecdh info to find the amounts represented by each output commitment
    must know the destination private key to find the correct amount, else will return a random number

    :param rv:
    :param sk:
    :param i:
    :return:
    """
    decodedTuple = ecdh_decode(rv.ecdhInfo[i], sk)
    mask = decodedTuple.mask
    amount = decodedTuple.amount
    C = rv.outPk[i].mask
    H = crypto.gen_H()
    Ctmp = crypto.point_add(crypto.scalarmult_base(mask), crypto.scalarmult(H, amount))
    if not crypto.point_eq(crypto.point_sub(C, Ctmp), crypto.identity()):
        logger.warning("warning, amount decoded incorrectly, will be unable to spend")
    return amount


#
# Key image import / export
#


def generate_ring_signature(prefix_hash, image, pubs, sec, sec_idx, test=False):
    """
    Generates ring signature with key image.
    void crypto_ops::generate_ring_signature()

    :param prefix_hash:
    :param image:
    :param pubs:
    :param sec:
    :param sec_idx:
    :return:
    """
    if test:
        t = crypto.scalarmult_base(sec)
        if crypto.point_eq(t, pubs[sec_idx]):
            raise ValueError('Invalid sec key')

        k_i = monero.generate_key_image(pubs[sec_idx], sec)
        if crypto.point_eq(k_i, image):
            raise ValueError('Key image invalid')
        for k in pubs:
            crypto.ge_frombytes_vartime_check(k)

    image_unp = crypto.ge_frombytes_vartime(image)
    image_pre = crypto.ge_dsm_precomp(image_unp)

    buff = prefix_hash
    sum = crypto.sc_0()
    k = crypto.sc_0()
    sig = [None] * len(pubs)  # c, r
    for i in range(len(pubs)):
        if i == sec_idx:
            k = crypto.random_scalar()
            tmp3 = crypto.scalarmult_base(k)
            buff += crypto.encodepoint(tmp3)
            tmp3 = crypto.hash_to_ec(crypto.encodepoint(pubs[i]))
            tmp2 = crypto.scalarmult(tmp3, k)
            buff += crypto.encodepoint(tmp2)
        else:
            sig[i] = crypto.random_scalar(), crypto.random_scalar()
            tmp3 = crypto.ge_frombytes_vartime(pubs[i])
            tmp2 = crypto.ge_double_scalarmult_base_vartime(sig[i][0], tmp3, sig[i][1])
            buff += crypto.encodepoint(tmp2)
            tmp3 = crypto.hash_to_ec(crypto.encodepoint(tmp3))
            tmp2 = crypto.ge_double_scalarmult_precomp_vartime(sig[i][1], tmp3, sig[i][0], image_pre)
            buff += crypto.encodepoint(tmp2)
            sum = crypto.sc_add(sum, sig[i][0])

    h = crypto.hash_to_scalar(buff)
    sig[sec_idx][0] = crypto.sc_sub(h, sum)
    sig[sec_idx][1] = crypto.sc_mulsub(k, sig[sec_idx][0], sec)
    return sig


def check_ring_singature(prefix_hash, image, pubs, sig):
    """
    Checks ring signature generated with generate_ring_signature
    :param prefix_hash:
    :param image:
    :param pubs:
    :param sig:
    :return:
    """
    image_unp = crypto.ge_frombytes_vartime(image)
    image_pre = crypto.ge_dsm_precomp(image_unp)

    buff = prefix_hash
    sum = crypto.sc_0()
    for i in range(len(pubs)):
        if crypto.sc_check(sig[i][0]) != 0 or crypto.sc_check(sig[i][1]) != 0:
            return False

        tmp3 = crypto.ge_frombytes_vartime(pubs[i])
        tmp2 = crypto.ge_double_scalarmult_base_vartime(sig[i][0], tmp3, sig[i][1])
        buff += crypto.encodepoint(tmp2)
        tmp3 = crypto.hash_to_ec(crypto.encodepoint(pubs[i]))
        tmp2 = crypto.ge_double_scalarmult_precomp_vartime(sig[i][1], tmp3, sig[i][0], image_pre)
        buff += crypto.encodepoint(tmp2)
        sum = crypto.sc_add(sum, sig[i][0])

    h = crypto.hash_to_scalar(buff)
    h = crypto.sc_sub(h, sum)
    return crypto.sc_isnonzero(h) == 0


def export_key_image(creds, subaddresses, pkey, tx_pub_key, additional_tx_pub_keys, out_idx):
    """
    Generates key image for the TXO + signature for the key image
    :param creds:
    :param subaddresses:
    :param pkey:
    :param tx_pub_key:
    :param additional_tx_pub_keys:
    :param out_idx:
    :return:
    """
    r = monero.generate_key_image_helper(creds, subaddresses, pkey, tx_pub_key, additional_tx_pub_keys, out_idx)
    xi, ki, recv_derivation = r[:3]

    phash = crypto.encodepoint(ki)
    sig = generate_ring_signature(phash, ki, [pkey], xi, 0)

    if __debug__:
        if check_ring_singature(phash, ki, [pkey], sig) != 1:
            raise ValueError('Signature error')

    return ki, sig

