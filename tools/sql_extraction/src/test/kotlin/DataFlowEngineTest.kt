package com.google.cloud.sqlecosystem.sqlextraction

import io.mockk.confirmVerified
import io.mockk.mockk
import io.mockk.spyk
import io.mockk.verify
import io.mockk.verifyOrder
import kotlin.test.Test

class DataFlowEngineTest {
    @Test
    fun `visitScope pushes and pops env scope`() {
        val env = mockk<Environment>(relaxUnitFun = true)
        val func = spyk<() -> Unit> {}

        val engine = DataFlowEngine(env)
        engine.visitScope { func() }

        verifyOrder {
            env.pushScope()
            func()
            env.popScope()
        }
        confirmVerified()
    }

    @Test
    fun `visitMethod pushes and pops env scope`() {
        val env = mockk<Environment>(relaxUnitFun = true)
        val func = spyk<() -> Unit> {}

        val engine = DataFlowEngine(env)
        engine.visitMethod { func() }

        verifyOrder {
            env.pushScope()
            func()
            env.popScope()
        }
        confirmVerified()
    }

    @Test
    fun `declareVariable declares variable`() {
        val env = mockk<Environment>(relaxUnitFun = true)
        val varName = "stub"

        val engine = DataFlowEngine(env)
        engine.declareVariable(varName)

        verify { env.declareVariable(varName) }
        confirmVerified()
    }

    @Test
    fun `addMethodParameter declares variable`() {
        val env = mockk<Environment>(relaxUnitFun = true)
        val varName = "stub"

        val engine = DataFlowEngine(env)
        engine.addMethodParameter(varName)

        verify { env.declareVariable(varName) }
        confirmVerified()
    }
}
