import sys
sys.path.append ('/Users/seinchin/Documents/Caltech/Arnold Lab/Programming tools/GPModel')
import gpkernel,gpmodel
import pandas as pd
import numpy as np
import math
import pytest
import scipy

seqs = pd.DataFrame([['R','Y','M','A'],['R','T','H','A'], ['R','T','M','A']],
                    index=['A','B','C'], columns=[0,1,2,3])
seqs = seqs.append(seqs.iloc[0])
seqs.index = ['A','B','C','A']

space = [('R'), ('Y', 'T'), ('M', 'H'), ('A')]
contacts = [(0,1),(2,3)]

class_Ys = pd.Series([-1,1,1,-1],index=seqs.index)
reg_Ys = pd.Series([-1,1,0.5,-.4],index=seqs.index)
ham = gpkernel.HammingKernel()
struct = gpkernel.StructureKernel (contacts,space)

test_seqs = pd.DataFrame([['R','T','H','A'],['R','Y','H','A']],index=['A','D'])





def test_regression ():

    print 'Testing constructors for regression models...'
    ham_model = gpmodel.GPModel(seqs,reg_Ys,ham)
    struct_model = gpmodel.GPModel(seqs,reg_Ys,struct)

    assert ham_model.K.equals(ham.make_K(seqs))
    assert struct_model.K.equals(struct.make_K(seqs))
    assert ham_model.l == len(seqs.index)
    assert struct_model.l ==  len(seqs.index)



    Y_mat = np.matrix(reg_Ys)
    for name,model in zip(['hamming','structure'],
                          [ham_model, struct_model]):
        print 'Testing regression with ' + name + ' model...'
        vp = 0.5
        vn = .2
        K_mat = np.matrix(model.K)
        Ky = vp*K_mat + np.eye(len(reg_Ys))*vn
        first = 0.5*Y_mat*np.linalg.inv(Ky)*Y_mat.T
        second = math.log(np.linalg.det(Ky))*0.5
        third = len(reg_Ys)*math.log(2*math.pi)*.5
        ML = first + second + third

        # because floating point precision
        assert close_enough(model.log_ML((vn,vp)), ML.item()), \
        name + 'log_ML fails: ' + ' '.join([str(first),str(second),str(third)])

        # test predictions
        kA = np.matrix([model.kern.calc_kernel(test_seqs.loc['A'],seq1,model.var_p) for seq1 \
                        in [seqs.iloc[i] for i in range(len(seqs.index))]])
        kD = np.matrix([model.kern.calc_kernel(test_seqs.loc['D'],seq1,model.var_p) for seq1 \
                        in [seqs.iloc[i] for i in range(len(seqs.index))]])
        EA = kA*np.linalg.inv(model.Ky)*Y_mat.T
        ED = kD*np.linalg.inv(model.Ky)*Y_mat.T
        k_star_A = model.kern.calc_kernel(test_seqs.loc['A'],test_seqs.loc['A'])*model.var_p
        k_star_D = model.kern.calc_kernel(test_seqs.loc['D'],test_seqs.loc['D'])*model.var_p
        var_A = k_star_A - kA*np.linalg.inv(model.Ky)*kA.T
        var_D = k_star_D - kD*np.linalg.inv(model.Ky)*kD.T

        predictions = model.predicts(test_seqs)

        assert close_enough(EA, predictions[0][0])
        assert close_enough(ED, predictions[1][0])
        assert close_enough(var_A, predictions[0][1])
        assert close_enough(var_D, predictions[1][1])

        [(E,v)] = model.predicts(test_seqs.loc[['D']])
        assert close_enough(E,ED)
        assert close_enough(v,var_D)

    print 'Regression models pass all tests.'




def test_classification ():
    print 'Testing constructors for classification models...'
    ham_model = gpmodel.GPModel(seqs,class_Ys,ham)
    struct_model = gpmodel.GPModel(seqs,class_Ys,struct)
    test_F = pd.Series([-.5,.5,.6,.1])

    assert ham_model.K.equals(ham.make_K(seqs))
    assert struct_model.K.equals(struct.make_K(seqs))
    assert ham_model.l == len(seqs.index)
    assert struct_model.l ==  len(seqs.index)


    for name,model in zip(['hamming','structure'],
                          [ham_model, struct_model]):
        print 'Testing classification with ' + name + ' model...'
        assert model.logistic_likelihood(1,0) == 0.5
        assert model.logistic_likelihood(-1,0) == 0.5
        pytest.raises(RuntimeError, "model.logistic_likelihood(-2,1)")

        assert model.log_logistic_likelihood(class_Ys,pd.Series([0,0,0,0])) == math.log(0.125/2)
        pytest.raises(RuntimeError, "model.log_logistic_likelihood(class_Ys,pd.Series([0,0,0]))")

        # Test the gradient and hessian functions
        glll = model.grad_log_logistic_likelihood(class_Ys, test_F)
        for i in range(model.l):
            for j in range(model.l):
                if i != j:
                    assert glll[i,j] == 0, 'Non-zero non-diagonal element of glll'
                else:
                    assert close_enough(glll[i,j], (class_Ys.iloc[i]+1)/2. -
                                        model.logistic_likelihood(1,test_F.iloc[i]))

        hess = model.hess (test_F)
        for i in range(model.l):
            for j in range(model.l):
                if i != j:
                    assert hess[i,j] == 0, 'Non-zero non-diagonal element of W'
                else:
                    pi_i = model.logistic_likelihood(1,test_F.iloc[i])
                    assert close_enough (hess[i,j], pi_i*(1-pi_i))

        # test find_F (Algorithm 3.1) by seeing if the result satisfies Eq 3.17 from RW
        f_hat = model.find_F()
        K = model.kern.make_K(seqs)
        K_mat = np.matrix(K)
        glll = np.matrix(np.diag(model.grad_log_logistic_likelihood(class_Ys,f_hat))).T
        f_check = K_mat*glll
        for fh, fc in zip(f_hat, f_check):
            assert close_enough(fh,fc), 'find_F fails for ' + name + ' model and var_p = 1.'

        vp = 0.1
        f_hat = model.find_F(var_p = vp)
        K_mat = K_mat*vp
        glll = np.matrix(np.diag(model.grad_log_logistic_likelihood(class_Ys,f_hat))).T
        f_check = K_mat*glll
        for fh, fc in zip(f_hat, f_check):
            assert close_enough(fh,fc), 'find_F fails for ' + name + ' model and var_p ~= 1.'

        # Test the functions that calculate marginal likelihood
        logq = model.logq(f_hat, var_p=vp)
        W = model.hess (f_hat)
        W_root = scipy.linalg.sqrtm(W)
        F_mat = np.matrix (f_hat)
        l = len(f_hat)
        L = np.linalg.cholesky (np.matrix(np.eye(l))+W_root*K_mat*W_root)
        b = W*F_mat.T + glll
        a = b - W_root*np.linalg.lstsq(L.T,np.linalg.lstsq(L,W_root*K_mat*b)[0])[0]
        check_q = 0.5*a.T*F_mat.T - model.log_logistic_likelihood(class_Ys, f_hat) + sum(np.log(np.diag(L)))
        assert close_enough(check_q,logq)
        assert close_enough(model.logistic_log_ML([vp]), check_q)

        # Test the function that is integrated
        v = 0.4
        m = 0.5
        for z in [0.5, 0, 10000, -10000]:
            val = 1./(1+np.exp(-z))/math.sqrt(2*math.pi*v)*math.exp(-(z-m)**2/2/v)
            assert close_enough(val, model.p_integral(z,m,v))
        for z in [np.inf, -np.inf]:
            assert close_enough(0., model.p_integral(z,m,v))

        # test predictions




    print 'Classification models pass all tests.'

def close_enough(f1,f2):
    return (f1-f2)**2 < 1e-7


if __name__=="__main__":
    #test_regression()
    test_classification()